"""Shared HTTP plumbing for the provider clients: timeouts, retries, redaction.

Four vendors, four different ways of saying "slow down", and no two error envelopes
alike. This module holds what they have in common so that
:mod:`app.search.tavily`, :mod:`app.search.serper`, :mod:`app.search.brave` and
:mod:`app.factcheck.google` can each be about one thing — how to build a request and
how to read a response — rather than each carrying its own copy of the failure
handling.

Two properties matter more than the mechanics.

**A failure must never be mistaken for an empty index.** Every path out of
:meth:`Http.fetch` either returns a parsed body or raises. Nothing returns ``[]``
on error, because the fan-out records "searched, found nothing" and "could not
search" as different outcomes and a swallowed exception collapses them — which is
how a dossier ends up telling a reader there is no evidence when the truth is that
nobody looked. See :class:`~app.domain.research.ProviderOutcome`. The fact-check
lookup in :mod:`app.factcheck.lookup` needs the same distinction for a stronger
reason: "no fact-checker has ruled on this" is a sentence about the world, and a
swallowed 403 would put it in a response unearned.

**A credential must never reach a log line or a response body.** Provider errors
are surfaced to clients with their detail attached, and provider messages
sometimes quote the request. :func:`redact` runs over every message this module
raises, and the API keys are held as ``SecretStr`` right up to the moment a header
is built.

This module knows no vendor's name and no provider family. :attr:`Http.error` is the
one hook: a subclass names the :class:`~app.core.errors.ProviderError` subclass its
failures should arrive as, so the same 401 handling produces ``search_error`` for a
search client and ``fact_check_error`` for a fact-check client.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from http import HTTPStatus
from typing import Any

import httpx

from app.core.errors import (
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.core.logging import get_logger

__all__ = ["Http", "ensure_parsed", "redact"]

logger = get_logger(__name__)

#: Statuses worth trying again. 429 is rate limiting, which is by definition
#: temporary; 5xx is the provider's own fault and often transient. Everything else
#: — a bad key, a malformed query, an exhausted plan — will fail identically on a
#: second attempt, so retrying it only makes the caller wait longer for the same
#: answer.
RETRYABLE: frozenset[int] = frozenset(
    {
        HTTPStatus.TOO_MANY_REQUESTS,
        HTTPStatus.INTERNAL_SERVER_ERROR,
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
    }
)

#: Tavily's non-standard quota codes: 432 is "key or plan limit exceeded" and 433
#: is "pay-as-you-go limit exceeded". Neither is in :class:`http.HTTPStatus`, and
#: neither is retryable — a quota does not refill in the next two seconds. They are
#: named here because a client that only branched on well-known codes would report
#: an exhausted plan as a generic bad gateway and send an operator looking in the
#: wrong place. 402 covers the same condition generically, and Google's fact-check
#: API returns 429 for a spent daily quota rather than any of these.
QUOTA_STATUSES: frozenset[int] = frozenset({402, 432, 433})

#: Longest this module will wait when a provider asks it to. Tavily's documented
#: ``retry-after`` on a development key is 60 seconds, which is far longer than a
#: request handler should hold a connection open for; past this the honest move is
#: to give up and let the outcome say why.
MAX_BACKOFF_SECONDS = 8.0

#: Base delay for the escalating wait between attempts, doubled each time.
#: Deliberately not jittered: three concurrent providers are not a thundering
#: herd, and a deterministic schedule is one a test can assert exactly. If this
#: ever fans out to dozens of keys, add jitter — with
#: :class:`random.SystemRandom`, since ruff's bandit rules reject bare ``random``.
BACKOFF_BASE_SECONDS = 0.5


def ensure_parsed(
    provider: str,
    *,
    received: int,
    parsed: int,
    error: type[ProviderError] = ProviderError,
) -> None:
    """Raise when a provider returned items and none of them could be read.

    The failure this exists to prevent is the quietest one available. If a
    provider renames a field — ``link`` to ``url``, ``organic`` to ``results`` —
    every item fails its check, the loop skips all of them, and the client returns
    an empty list. That list is indistinguishable from "this provider searched and
    found nothing", so the dossier tells a reader there is no evidence for a claim
    when in truth twenty pages came back and were dropped on the floor.

    Twenty items in and zero out is not an empty index; it is a broken parser. It
    raises, the fan-out records
    :attr:`~app.domain.research.ProviderStatus.FAILED`, and the dossier says so.

    Zero in and zero out is left alone: that is a real, reportable answer.

    ``error`` is the caller's family error class, so the raise reaches a client as
    ``search_error`` or ``fact_check_error`` rather than as a generic provider
    failure. It defaults to the base class rather than to either one, because a
    default of :class:`~app.core.errors.SearchError` is the kind that stays wrong
    silently in the one caller that is not a search client.
    """
    if received and not parsed:
        raise error(
            f"{provider} returned {received} results and none could be parsed — "
            "the response shape has probably changed",
            provider=provider,
            details={"received": received},
        )


def redact(text: str, *secrets: str) -> str:
    """``text`` with every occurrence of any of ``secrets`` replaced.

    The last line of defence rather than the first: keys are kept in ``SecretStr``
    and only unwrapped into a header, so in principle nothing here has one to
    find. In practice provider error messages sometimes echo the request, and a
    ``ProviderError``'s detail is returned to the client — so the message is
    filtered on the way out regardless. Short secrets are ignored, since replacing
    every two-character substring would mangle the message without protecting
    anything.
    """
    for secret in secrets:
        if secret and len(secret) >= 8:
            text = text.replace(secret, "***")
    return text


class Http:
    """A provider's HTTP transport: one connection pool, bounded retries.

    Subclasses supply :attr:`name` and call :meth:`fetch`. The client is created on
    first use rather than in ``__init__`` so that constructing a provider — which
    the registry does per request — costs nothing, and so a provider that is
    skipped for want of a key never opens a socket.
    """

    #: Registered provider name. Also what appears in
    #: :attr:`~app.domain.research.Retrieval.provider`, so it is part of the API.
    name: str = "http"

    #: The :class:`~app.core.errors.ProviderError` subclass this client's failures
    #: are raised as, and therefore the ``code`` a client sees on a partial result.
    #: Set it on every concrete subclass: the default is the base class, which
    #: renders as ``provider_error`` and is correct for nothing in particular. That
    #: is deliberate — defaulting to :class:`~app.core.errors.SearchError` would
    #: make a forgotten override invisible in exactly the client that is not a
    #: search client.
    error: type[ProviderError] = ProviderError

    def __init__(
        self,
        *,
        timeout: float,
        attempts: int = 3,
        secrets: tuple[str, ...] = (),
    ) -> None:
        self._timeout = timeout
        #: Total tries, not retries: 1 means no retry at all.
        self._attempts = max(1, attempts)
        self._secrets = secrets
        self._client: httpx.AsyncClient | None = None

    # ----------------------------------------------------------- lifecycle ----

    def _open(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                follow_redirects=True,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def aclose(self) -> None:
        """Release the connection pool. Safe to call twice, and on an unused
        client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # --------------------------------------------------------------- fetch ----

    async def fetch(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """One request, retried where retrying can help, decoded as JSON.

        Raises rather than returning a sentinel, always:

        :class:`~app.core.errors.ProviderTimeoutError` (504)
            The provider did not answer inside ``timeout``.
        :class:`~app.core.errors.ProviderUnavailableError` (503)
            Unreachable, or still failing after the last attempt, or out of
            quota — the cases where the useful thing to tell a caller is "try
            later", not "your request was wrong".
        :attr:`error` (502 by default)
            Anything else: a rejected key, a malformed query, a body that is not
            the JSON it claimed to be. The subclass chooses the class, so the same
            rejected key surfaces as ``search_error`` from a search client and
            ``fact_check_error`` from a fact-check client.
        """
        client = self._open()
        last: Exception | None = None

        for attempt in range(1, self._attempts + 1):
            try:
                response = await client.request(
                    method, url, headers=headers, params=params, json=json
                )
            except httpx.TimeoutException as exc:
                # Not retried. A timeout has already spent the caller's budget;
                # spending it twice turns one slow provider into a slow dossier.
                raise ProviderTimeoutError(
                    f"{self.name} did not respond within {self._timeout:g}s",
                    provider=self.name,
                ) from exc
            except httpx.HTTPError as exc:
                last = exc
                if attempt == self._attempts:
                    raise ProviderUnavailableError(
                        self._clean(f"{self.name} is unreachable: {exc}"),
                        provider=self.name,
                    ) from exc
                await self._wait(attempt, None)
                continue

            if response.is_success:
                return self._decode(response)

            if response.status_code in RETRYABLE and attempt < self._attempts:
                logger.warning(
                    "search provider retrying",
                    extra={
                        "provider": self.name,
                        "status": response.status_code,
                        "attempt": attempt,
                    },
                )
                await self._wait(attempt, response)
                continue

            raise self._error(response)

        # Unreachable: the loop either returns, raises, or continues, and the last
        # iteration cannot continue. Kept so the type checker sees a total
        # function and so a future edit to the loop cannot fall out silently.
        raise ProviderUnavailableError(
            self._clean(f"{self.name} failed after {self._attempts} attempts: {last}"),
            provider=self.name,
        )

    # -------------------------------------------------------------- errors ----

    def _error(self, response: httpx.Response) -> ProviderError:
        """The exception for a non-retryable failure, or a spent retry budget.

        The provider's own message is included when there is one, because "401"
        alone does not tell an operator whether the key is missing, wrong or
        expired. It is passed through :func:`redact` first: several of these APIs
        echo parts of the request back, and this detail reaches the client.
        """
        status = response.status_code
        detail = self._clean(_message(response))

        if status in QUOTA_STATUSES:
            return ProviderUnavailableError(
                f"{self.name} quota exhausted ({status}): {detail}",
                provider=self.name,
                details={"status": status},
            )
        if status == HTTPStatus.TOO_MANY_REQUESTS:
            return ProviderUnavailableError(
                f"{self.name} rate limit exceeded: {detail}",
                provider=self.name,
                details={"status": status},
            )
        if status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
            return self.error(
                f"{self.name} rejected the API key ({status}): {detail}",
                provider=self.name,
                details={"status": status},
            )
        if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
            return ProviderUnavailableError(
                f"{self.name} returned {status}: {detail}",
                provider=self.name,
                details={"status": status},
            )
        return self.error(
            f"{self.name} returned {status}: {detail}",
            provider=self.name,
            details={"status": status},
        )

    def _decode(self, response: httpx.Response) -> Any:
        """The JSON body, or an :attr:`error` naming what arrived instead.

        A 200 carrying HTML — a captive portal, a proxy error page, a provider
        outage served by a CDN — is a failure, and it has to be raised rather than
        parsed into zero results.
        """
        try:
            return response.json()
        except ValueError as exc:
            kind = response.headers.get("content-type", "unknown")
            raise self.error(
                f"{self.name} returned {kind} where JSON was expected",
                provider=self.name,
            ) from exc

    def _clean(self, text: str) -> str:
        return redact(text, *self._secrets)

    # ------------------------------------------------------------ backoff ----

    async def _wait(self, attempt: int, response: httpx.Response | None) -> None:
        """Sleep before the next attempt, honouring the provider if it said how
        long.

        The three providers signal this three ways, and none of them is
        guaranteed, so all are read and a computed backoff is the floor:

        * Tavily documents ``retry-after`` on a 429, in seconds — possibly, per
          its own docs, as an HTTP-date instead.
        * Brave documents no ``Retry-After`` at all and directs callers to
          ``X-RateLimit-Reset``, a comma-separated list of relative seconds, one
          per quota window. The smallest is the one that has to elapse before the
          next request can succeed.
        * Serper documents nothing, which is why there is a computed fallback.
        """
        backoff = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
        if response is not None:
            asked = _retry_after(response)
            if asked is not None:
                backoff = max(backoff, asked)
        await asyncio.sleep(min(backoff, MAX_BACKOFF_SECONDS))


def _message(response: httpx.Response) -> str:
    """A human-readable reason out of whichever error envelope arrived.

    Three shapes, all documented, none shared:

    * Tavily — ``{"detail": {"error": "..."}}``
    * Serper — ``{"message": "...", "statusCode": 403}``
    * Brave  — ``{"type": "ErrorResponse", "error": {...}, "time": 0}``, whose
      inner object is undocumented; its reference page collapses the child
      attributes and they could not be read.

    So this looks for each in turn and falls back to the raw text, truncated. The
    fallback is the important part: Brave's inner shape is unknown, and an
    unrecognised body still has to produce something an operator can act on.
    """
    try:
        body = response.json()
    except ValueError:
        return _clip(response.text)

    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, dict) and isinstance(detail.get("error"), str):
            return detail["error"]
        if isinstance(detail, str):
            return detail
        if isinstance(body.get("message"), str):
            return body["message"]
        error = body.get("error")
        if isinstance(error, str):
            return error
        if isinstance(error, dict):
            for key in ("message", "detail", "code"):
                if isinstance(error.get(key), str):
                    return error[key]
            return _clip(str(error))
    return _clip(response.text)


def _retry_after(response: httpx.Response) -> float | None:
    """Seconds the provider asked for, from whichever header it used.

    Both headers are consulted, and a malformed ``retry-after`` falls through to
    the other rather than ending the search: a provider that sends an unreadable
    value in one header has not thereby withdrawn what it said in the other.
    """
    asked = _seconds(response.headers.get("retry-after"))
    if asked is not None:
        return asked

    # Brave: relative seconds per quota window, e.g. "1, 1419704". The nearest
    # window is the one blocking the next request; the monthly one is not worth
    # waiting for and MAX_BACKOFF_SECONDS caps it anyway.
    reset = response.headers.get("x-ratelimit-reset")
    if reset:
        windows = [
            float(part.strip())
            for part in reset.split(",")
            if part.strip().replace(".", "", 1).isdigit()
        ]
        if windows:
            return min(windows)
    return None


def _seconds(raw: str | None) -> float | None:
    """A ``Retry-After`` value as seconds from now, in either documented form."""
    if not raw:
        return None
    value = raw.strip()
    if value.isdigit():
        return float(value)
    # Tavily's docs leave open that this may be an HTTP-date rather than a count
    # of seconds, so try that before giving up on the header.
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def _clip(text: str, limit: int = 200) -> str:
    """Bound an error body before it goes into a message.

    An HTML error page is tens of kilobytes and none of it helps. The limit is
    small enough to keep a log line readable and large enough for any real API
    error string.
    """
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else f"{flat[:limit]}…"
