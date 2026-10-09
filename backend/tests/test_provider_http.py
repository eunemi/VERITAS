"""Transport behaviour: what gets sent, what gets retried, and what gets raised.

The rule these tests exist to hold down is the one in :mod:`app.providers.http`'s
docstring: **a failure must never be mistaken for an empty index.** Every test below
that ends in ``pytest.raises`` is asserting that some flavour of broken provider
produces an exception rather than a list — because the fan-out reports "searched,
found nothing" and "could not search" as different outcomes, and a swallowed error
collapses them into the first.

The requests are driven through :class:`httpx.MockTransport`. ``Http._open`` builds
its own pool and takes no transport argument — a parameter that existed only so
tests could inject one — so :func:`wire` assigns the private attribute instead. That
is a deliberate reach into the object: the alternative is production surface whose
only caller is a test.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import (
    FactCheckError,
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    SearchError,
)
from app.providers import http as http_module
from app.providers.http import (
    MAX_BACKOFF_SECONDS,
    Http,
    ensure_parsed,
    redact,
)
from app.search.brave import BraveClient
from app.search.tavily import TavilyClient

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)

KEY = "tvly-secret-key-value"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        TAVILY_API_KEY=KEY,
        BRAVE_API_KEY="brave-secret-key-value",
        SEARCH_ATTEMPTS=3,
        SEARCH_TIMEOUT_SECONDS=5.0,
    )


@pytest.fixture
def slept(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Every backoff the client asked for, without waiting for any of them.

    The delays are asserted rather than skipped: ``_wait`` is where three different
    providers' rate-limit conventions get reconciled, so how long it sleeps is
    behaviour, not an implementation detail.
    """
    calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        calls.append(seconds)

    monkeypatch.setattr(http_module.asyncio, "sleep", fake_sleep)
    return calls


def wire(
    client: Http, handler: Callable[[httpx.Request], httpx.Response]
) -> list[httpx.Request]:
    """Point ``client`` at ``handler`` and return the list it records requests in."""
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client._client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return seen


def replies(*responses: httpx.Response) -> Callable[[httpx.Request], httpx.Response]:
    """A handler that returns each response in turn, then repeats the last."""
    queue = list(responses)

    def handler(_request: httpx.Request) -> httpx.Response:
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return handler


def raiser(exc: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


# ------------------------------------------------------------- what is sent ----


async def test_tavily_sends_the_documented_body(settings: Settings) -> None:
    """Notably: no generated answer and no raw page bodies."""
    client = TavilyClient(settings)
    seen = wire(client, replies(httpx.Response(200, json={"results": []})))

    await client.search("who won", max_results=99, now=NOW)

    body = json.loads(seen[0].content)
    assert body["query"] == "who won"
    assert body["include_answer"] is False
    assert body["include_raw_content"] is False
    # Clamped to Tavily's documented ceiling rather than passed through.
    assert body["max_results"] == 20
    assert body["topic"] == "general"
    assert seen[0].headers["authorization"] == f"Bearer {KEY}"


async def test_brave_sends_text_decorations_off(settings: Settings) -> None:
    """The single most important query parameter in this package.

    Left at its default, Brave injects highlight markers into ``description`` — and
    every "verbatim" quote sliced out of that string would contain characters the
    publisher never wrote.
    """
    client = BraveClient(settings)
    seen = wire(client, replies(httpx.Response(200, json={"web": {"results": []}})))

    await client.search("who won", max_results=50, now=NOW)

    params = seen[0].url.params
    assert params["text_decorations"] == "false"
    assert params["spellcheck"] == "false"
    assert params["result_filter"] == "web"
    #: A string because that is what a query string holds — 50 was asked for and
    #: Brave's ceiling of 20 is what went out.
    assert params["count"] == "20"
    assert seen[0].headers["x-subscription-token"] == "brave-secret-key-value"


# ----------------------------------------------------------------- retrying ----


async def test_retries_a_rate_limit_then_succeeds(
    settings: Settings, slept: list[float]
) -> None:
    client = TavilyClient(settings)
    seen = wire(
        client,
        replies(
            httpx.Response(429, json={"detail": {"error": "too fast"}}),
            httpx.Response(200, json={"results": []}),
        ),
    )

    assert await client.search("q", now=NOW) == []
    assert len(seen) == 2
    assert slept == [0.5]


async def test_honours_a_retry_after_in_seconds(
    settings: Settings, slept: list[float]
) -> None:
    client = TavilyClient(settings)
    wire(
        client,
        replies(
            httpx.Response(429, json={}, headers={"Retry-After": "3"}),
            httpx.Response(200, json={"results": []}),
        ),
    )

    await client.search("q", now=NOW)

    assert slept == [3.0]


async def test_honours_braves_rate_limit_reset_header(
    settings: Settings, slept: list[float]
) -> None:
    """Brave sends no ``Retry-After``; it sends relative seconds per quota window.

    The nearest window is the one blocking the next request. The monthly one — the
    second number — is not something to wait for.
    """
    client = BraveClient(settings)
    wire(
        client,
        replies(
            httpx.Response(429, json={}, headers={"X-RateLimit-Reset": "1, 1419704"}),
            httpx.Response(200, json={"web": {"results": []}}),
        ),
    )

    await client.search("q", now=NOW)

    assert slept == [1.0]


async def test_caps_an_absurd_retry_after(
    settings: Settings, slept: list[float]
) -> None:
    """A provider asking for ten minutes does not get to hold a request handler."""
    client = TavilyClient(settings)
    wire(
        client,
        replies(
            httpx.Response(429, json={}, headers={"Retry-After": "600"}),
            httpx.Response(200, json={"results": []}),
        ),
    )

    await client.search("q", now=NOW)

    assert slept == [MAX_BACKOFF_SECONDS]


async def test_gives_up_after_the_last_attempt(
    settings: Settings, slept: list[float]
) -> None:
    client = TavilyClient(settings)
    seen = wire(client, replies(httpx.Response(503, json={})))

    with pytest.raises(ProviderUnavailableError):
        await client.search("q", now=NOW)

    # Three attempts total, so two waits: SEARCH_ATTEMPTS counts tries, not retries.
    assert len(seen) == 3
    assert slept == [0.5, 1.0]


async def test_does_not_retry_a_rejected_key(
    settings: Settings, slept: list[float]
) -> None:
    """A bad key fails identically on the second attempt; retrying only delays it."""
    client = TavilyClient(settings)
    seen = wire(client, replies(httpx.Response(401, json={})))

    with pytest.raises(SearchError):
        await client.search("q", now=NOW)

    assert len(seen) == 1
    assert slept == []


async def test_a_timeout_is_not_retried(settings: Settings, slept: list[float]) -> None:
    """A timeout has already spent the caller's budget once."""
    client = TavilyClient(settings)
    seen = wire(client, raiser(httpx.TimeoutException("too slow")))

    with pytest.raises(ProviderTimeoutError, match="5s"):
        await client.search("q", now=NOW)

    assert len(seen) == 1
    assert slept == []


async def test_a_connection_error_is_retried_then_reported(
    settings: Settings, slept: list[float]
) -> None:
    client = TavilyClient(settings)
    seen = wire(client, raiser(httpx.ConnectError("no route")))

    with pytest.raises(ProviderUnavailableError, match="unreachable"):
        await client.search("q", now=NOW)

    assert len(seen) == 3
    assert slept == [0.5, 1.0]


# ------------------------------------------------------------------- errors ----


async def test_a_quota_status_is_reported_as_unavailable(settings: Settings) -> None:
    """432 is Tavily's plan limit. Not in ``http.HTTPStatus``, and not a client bug.

    Reporting it as a generic bad gateway would send an operator looking at the
    network when the answer is that the month's credits are gone.
    """
    client = TavilyClient(settings)
    wire(
        client,
        replies(httpx.Response(432, json={"detail": {"error": "plan limit exceeded"}})),
    )

    with pytest.raises(ProviderUnavailableError, match="quota exhausted") as caught:
        await client.search("q", now=NOW)

    assert "plan limit exceeded" in str(caught.value)


async def test_the_api_key_never_reaches_the_error_message(
    settings: Settings,
) -> None:
    """Providers echo the request. The detail on this error reaches a client."""
    client = TavilyClient(settings)
    wire(
        client,
        replies(
            httpx.Response(
                401,
                json={"detail": {"error": f"invalid token {KEY} for this account"}},
            )
        ),
    )

    with pytest.raises(SearchError) as caught:
        await client.search("q", now=NOW)

    assert KEY not in str(caught.value)
    assert "***" in str(caught.value)


async def test_a_200_carrying_html_is_a_failure(settings: Settings) -> None:
    """A captive portal or a CDN outage page. Parsing it would yield zero results."""
    client = TavilyClient(settings)
    wire(
        client,
        replies(
            httpx.Response(
                200,
                text="<html><body>Gateway Error</body></html>",
                headers={"content-type": "text/html"},
            )
        ),
    )

    with pytest.raises(SearchError, match="text/html"):
        await client.search("q", now=NOW)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        pytest.param({"detail": {"error": "tavily said no"}}, "tavily said no"),
        pytest.param(
            {"message": "serper said no", "statusCode": 400}, "serper said no"
        ),
        pytest.param(
            {"type": "ErrorResponse", "error": {"detail": "brave said no"}},
            "brave said no",
        ),
        pytest.param({"detail": "a plain string"}, "a plain string"),
    ],
)
async def test_reads_each_providers_error_envelope(
    settings: Settings, body: dict[str, object], expected: str
) -> None:
    """Three vendors, three shapes, none shared. All of them have to be legible."""
    client = TavilyClient(settings)
    wire(client, replies(httpx.Response(400, json=body)))

    with pytest.raises(SearchError, match=expected):
        await client.search("q", now=NOW)


async def test_an_unrecognised_error_body_still_says_something(
    settings: Settings,
) -> None:
    """Brave's inner error object is undocumented, so the fallback is load-bearing."""
    client = TavilyClient(settings)
    wire(client, replies(httpx.Response(400, text="upstream refused " + "x" * 500)))

    with pytest.raises(SearchError, match="upstream refused") as caught:
        await client.search("q", now=NOW)

    # Clipped: an HTML error page is tens of kilobytes and none of it helps.
    assert len(str(caught.value)) < 400


# --------------------------------------------------------------- lifecycle ----


async def test_aclose_is_safe_on_an_unused_client(settings: Settings) -> None:
    client = TavilyClient(settings)

    await client.aclose()
    await client.aclose()


async def test_aclose_releases_the_pool(settings: Settings) -> None:
    client = TavilyClient(settings)
    wire(client, replies(httpx.Response(200, json={"results": []})))
    pool = client._client

    await client.search("q", now=NOW)
    await client.aclose()

    assert pool is not None
    assert client._client is None


# ------------------------------------------------------------------ helpers ----


def test_ensure_parsed_raises_when_everything_was_dropped() -> None:
    """The quietest possible failure, made loud."""
    with pytest.raises(SearchError, match="none could be parsed"):
        ensure_parsed("tavily", received=20, parsed=0, error=SearchError)


def test_ensure_parsed_defaults_to_the_base_provider_error() -> None:
    """A forgotten ``error=`` must not silently claim to be a search failure.

    The default is :class:`ProviderError` rather than
    :class:`~app.core.errors.SearchError` precisely so that the one caller which is
    not a search client — the fact-check lookup — cannot inherit the wrong code by
    omission.
    """
    with pytest.raises(ProviderError) as caught:
        ensure_parsed("somebody", received=20, parsed=0)

    assert not isinstance(caught.value, SearchError)
    assert caught.value.code == "provider_error"


def test_ensure_parsed_uses_the_error_class_it_was_given() -> None:
    with pytest.raises(FactCheckError) as caught:
        ensure_parsed("google", received=5, parsed=0, error=FactCheckError)

    assert caught.value.code == "fact_check_error"
    assert caught.value.details == {"received": 5, "provider": "google"}


def test_ensure_parsed_allows_a_genuinely_empty_response() -> None:
    ensure_parsed("tavily", received=0, parsed=0, error=SearchError)


def test_ensure_parsed_allows_a_partial_read() -> None:
    """One malformed item among twenty is not a schema change."""
    ensure_parsed("tavily", received=20, parsed=19, error=SearchError)


async def test_http_error_hook_decides_the_class_a_failure_arrives_as() -> None:
    """The same 400 is a different error code for a different family of client."""

    class Lookup(Http):
        name = "google"
        error = FactCheckError

    client = Lookup(timeout=5.0, attempts=1)
    wire(client, replies(httpx.Response(400, json={"message": "bad query"})))

    with pytest.raises(FactCheckError, match="bad query"):
        await client.fetch("GET", "https://example.test", headers={})


async def test_http_error_hook_defaults_to_the_base_class() -> None:
    """A subclass that forgets :attr:`Http.error` gets a code that reads as unset."""

    class Nameless(Http):
        name = "nameless"

    client = Nameless(timeout=5.0, attempts=1)
    wire(client, replies(httpx.Response(400, text="nope")))

    with pytest.raises(ProviderError) as caught:
        await client.fetch("GET", "https://example.test", headers={})

    assert not isinstance(caught.value, SearchError)
    assert caught.value.code == "provider_error"


def test_redact_replaces_a_secret() -> None:
    assert redact(f"token {KEY} rejected", KEY) == "token *** rejected"


def test_redact_ignores_a_short_secret() -> None:
    """Replacing every two-character substring would mangle the message instead."""
    assert redact("abc is not a key", "abc") == "abc is not a key"


def test_redact_with_no_secrets_is_a_no_op() -> None:
    assert redact("nothing to hide") == "nothing to hide"
