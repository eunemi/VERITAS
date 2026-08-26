"""Google's Fact Check Tools API — the index of what fact-checkers have published.

Verified against Google's own reference for ``GET
factchecktools.googleapis.com/v1alpha1/claims:search`` and the ``Claim`` /
``ClaimReview`` / ``Publisher`` schemas it returns.

This is not a search engine and it is not an oracle. It is an index of
`ClaimReview <https://schema.org/ClaimReview>`_ markup that publishers put on their own
pages, which makes it the one provider in this codebase whose results were written by
people doing the same job as this service. That makes it valuable and it also makes it
the easiest thing here to misuse, so three properties of the response shape are worth
stating before any of the code below makes sense.

**``Claim.text`` is Google's claim, not the query.** The API takes a query string and
returns the claims in its index that best match it — so for a claim nobody has reviewed,
the best match is a *different* claim about the same subject. Reporting that record's
rating as the verdict on the caller's claim would be a fabrication of relevance with
every character genuine. This client therefore returns
:attr:`~app.domain.factcheck.ReviewedClaim.text` verbatim and scores nothing;
:func:`app.research.reviews.select` decides what bears on the claim, and the wording
travels all the way to the reader either way.

**``textualRating`` has no scale.** Google's entire documentation for the field is
"Textual rating. For instance, 'Mostly false'." — no enum, no bounds, no numeric
sibling. That is an accurate description of a field holding thousands of distinct
publisher-authored strings, and it is why this client copies it and stops. Reading it is
:func:`app.research.reviews.read_stance`'s job.

**Nothing is required.** The reference marks no field of ``Claim`` or ``ClaimReview`` as
required, so every one is treated as absent-able. Two are load-bearing anyway and a
record missing either is dropped rather than reported with a hole in it: a claim with no
``text`` cannot be shown to a reader, and a review with no ``url`` is a verdict this
service could not substantiate if asked.

Two deliberate limits:

*Only the first page is read.* ``nextPageToken`` is ignored. The API ranks by relevance,
so page two of a claim's own wording is where the loosely-related records are — the ones
:data:`app.research.reviews.MIN_MATCH` exists to drop — and following it would multiply
the request count per claim against a shared daily quota. What this cannot cost is a
false "nobody has reviewed this": that would require page one to be empty, in which case
there is no token.

*The key travels in a header.* ``x-goog-api-key``, which Google documents as the
recommended mechanism, rather than the ``key`` query parameter — which Google's own
documentation warns exposes the key "to theft through URL scans", and which would put it
in every proxy log and error string between here and Mountain View.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.config import Settings
from app.core.errors import ConfigurationError, FactCheckError
from app.domain import Review, ReviewedClaim
from app.providers.dates import parse_absolute
from app.providers.http import Http, ensure_parsed

__all__ = ["MAX_PAGE_SIZE", "MAX_QUERY_CHARS", "GoogleFactCheckClient", "build"]

#: Ceiling on ``pageSize``.
#:
#: Google documents the default (10) and no maximum. 20 is this application's choice,
#: matched to the three search providers' documented ceilings so that no single provider
#: can quietly dominate a dossier.
MAX_PAGE_SIZE = 20

#: Ceiling on the query string, in characters.
#:
#: Also undocumented, and the reason for guessing rather than sending whatever arrives:
#: ``POST /research`` accepts caller-supplied claim strings, so "one sentence" is a
#: convention and not a guarantee, and an over-long query would spend this provider's
#: whole contribution for that claim on a 400. Truncation loses recall visibly; a 400
#: loses the lookup entirely.
#:
#: Deliberately not imported from :func:`app.search.brave.clamp_query`, which enforces a
#: limit Brave documents together with a word count Brave also documents. The two
#: numbers agreeing is a coincidence, and sharing the function would put a dependency
#: from this package onto :mod:`app.search` — a false edge between two provider families
#: that have nothing to do with each other.
MAX_QUERY_CHARS = 400


class GoogleFactCheckClient(Http):
    """Looks up published fact checks through Google's Fact Check Tools API."""

    name = "google"
    url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
    error = FactCheckError

    def __init__(self, settings: Settings) -> None:
        if settings.GOOGLE_FACT_CHECK_API_KEY is None:
            raise ConfigurationError(
                "GOOGLE_FACT_CHECK_API_KEY is not set", details={"provider": self.name}
            )
        self._key = settings.GOOGLE_FACT_CHECK_API_KEY.get_secret_value()
        super().__init__(
            timeout=settings.FACT_CHECK_TIMEOUT_SECONDS,
            attempts=settings.FACT_CHECK_ATTEMPTS,
            secrets=(self._key,),
        )

    async def lookup(
        self,
        query: str,
        *,
        max_results: int = 10,
        language: str = "",
        max_age_days: int = 0,
        now: datetime,
    ) -> list[ReviewedClaim]:
        """Records matching ``query``, in Google's relevance order.

        ``language`` and ``max_age_days`` are omitted from the request when unset
        rather than sent with a neutral value, because neither has a documented
        neutral value: ``languageCode=""`` and ``maxAgeDays=0`` are guesses about how
        the API reads an empty filter, and a filter that silently matched nothing
        would look exactly like a claim nobody has reviewed.

        ``maxAgeDays`` measures from "the claim date or review date, whichever is
        newer", per Google. Worth knowing before setting it: a 2019 claim reviewed
        last week is inside a 30-day window, which is the correct behaviour for this
        service — a resurfaced old claim is precisely what a lookup should find.
        """
        if not query.strip():
            # Not an empty result. The API requires `query` (absent a publisher
            # filter, which this client does not send), so this would be a 400 — and
            # reporting it as "nobody has reviewed this claim" would state something
            # about the world on the strength of a bug in the caller.
            raise FactCheckError(
                f"{self.name} was asked to look up an empty query",
                provider=self.name,
            )

        params: dict[str, Any] = {
            "query": _clamp(query),
            "pageSize": max(1, min(max_results, MAX_PAGE_SIZE)),
        }
        if language:
            params["languageCode"] = language
        if max_age_days > 0:
            params["maxAgeDays"] = max_age_days

        payload = await self.fetch(
            "GET",
            self.url,
            # Google documents the request body as required-empty for this method,
            # so there is deliberately no `json=`.
            headers={"x-goog-api-key": self._key},
            params=params,
        )
        return self.parse(payload, now=now)

    def parse(self, payload: Any, *, now: datetime) -> list[ReviewedClaim]:
        """Turn a decoded response body into records.

        Public so a recorded response can be parsed in a test without a network.

        A missing ``claims`` key is zero records, which is the API's documented way of
        saying nothing in the index matched — a real and common answer for a claim too
        new or too obscure to have been reviewed. A ``claims`` key that is not a list
        raises instead, because that is the contract changing, and the two must not
        collapse: one of them is a fact about the world and the other is a fact about
        this code, and only the second is fixable.
        """
        if not isinstance(payload, dict):
            raise FactCheckError(
                f"{self.name} returned {type(payload).__name__} where an object "
                "was expected",
                provider=self.name,
            )
        raw = payload.get("claims")
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise FactCheckError(
                f"{self.name} returned a non-array 'claims'",
                provider=self.name,
                details={"keys": sorted(k for k in payload if isinstance(k, str))},
            )

        records: list[ReviewedClaim] = []
        for item in raw:
            record = _record(item, now=now)
            if record is not None:
                records.append(record)
        # A schema change — `claimReview` renamed, `text` renamed — would otherwise
        # arrive as "no fact-checker has ruled on this claim", the one outcome that is
        # both wrong and invisible. Every claim in a review index has at least one
        # review, so dropping all of them means this code stopped understanding the
        # response rather than that the response was empty.
        ensure_parsed(
            self.name, received=len(raw), parsed=len(records), error=self.error
        )
        return records


def _record(item: Any, *, now: datetime) -> ReviewedClaim | None:
    """One ``Claim``, or ``None`` when there is nothing reportable in it."""
    if not isinstance(item, dict):
        return None
    text = item.get("text")
    if not isinstance(text, str) or not text.strip():
        return None

    reviews = _reviews(item.get("claimReview"), now=now)
    if not reviews:
        # A claim with no readable review is not a fact check. Reporting it would put
        # a row in the dossier that says a verdict exists and cannot show one.
        return None

    claimed_at, date_text = _when(item.get("claimDate"), now=now)
    return ReviewedClaim(
        text=text,
        reviews=reviews,
        claimant=_text(item.get("claimant")),
        claimed_at=claimed_at,
        date_text=date_text,
    )


def _reviews(raw: Any, *, now: datetime) -> tuple[Review, ...]:
    """Every ``ClaimReview`` with a URL, in the order Google returned them."""
    if not isinstance(raw, list):
        return ()

    reviews: list[Review] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url:
            continue
        publisher, site = _publisher(item.get("publisher"))
        reviewed_at, date_text = _when(item.get("reviewDate"), now=now)
        reviews.append(
            Review(
                publisher=publisher,
                site=site,
                url=url,
                # Verbatim, and empty when Google sent nothing. See the module
                # docstring: reading this string is not a client's job.
                rating=_text(item.get("textualRating")),
                title=_text(item.get("title")),
                language=_text(item.get("languageCode")),
                reviewed_at=reviewed_at,
                date_text=date_text,
                # `stance` and `stance_from` are left at their defaults on purpose.
            )
        )
    return tuple(reviews)


def _publisher(raw: Any) -> tuple[str, str]:
    """``publisher.name`` and ``publisher.site``, each only if Google sent it.

    Not defaulted to each other. ``site`` is documented as derived from the review URL
    — "This value of this field is based purely on the claim review URL" — so putting
    it in ``publisher`` would present a hostname as an organisation's name for its own
    verdict, which is a claim Google did not make.
    """
    if not isinstance(raw, dict):
        return "", ""
    return _text(raw.get("name")), _text(raw.get("site"))


def _when(value: Any, *, now: datetime) -> tuple[datetime | None, str | None]:
    """A Google timestamp, parsed, keeping the original string either way.

    Google documents both date fields as RFC 3339 UTC with up to nine fractional
    digits, which :func:`app.providers.dates.parse_absolute` already reads — including
    the nine digits, which it truncates to microseconds rather than rejecting.

    :func:`app.providers.dates.resolve` is deliberately not used. Its plausibility
    floor is written for web publication dates, and one of these fields is a *claim*
    date: a politician repeating something first said decades ago is exactly what a
    fact-check lookup is for, and a floor at the start of the web would silently drop
    the date that made the record interesting.

    A date in the future is refused, which is the one bound worth keeping. It cannot
    be true of either field, it sorts wrong wherever it lands, and refusing it costs
    nothing because ``date_text`` still carries what arrived.
    """
    if not isinstance(value, str) or not value.strip():
        return None, None
    found = parse_absolute(value)
    if found is None or found > now:
        return None, value
    return found, value


def _clamp(query: str, *, chars: int = MAX_QUERY_CHARS) -> str:
    """``query`` cut to :data:`MAX_QUERY_CHARS` on a word boundary.

    Word boundary rather than mid-token because half a name is a different search
    term, and a lookup for ``"Kamala Har"`` would return records this dossier would
    then attribute to a claim nobody made.
    """
    words = query.split()
    out = " ".join(words)
    while len(out) > chars and words:
        words.pop()
        out = " ".join(words)
    return out


def _text(value: Any) -> str:
    """A string field, or ``""`` when the provider omitted it."""
    return value if isinstance(value, str) else ""


def build(settings: Settings) -> GoogleFactCheckClient:
    """Factory for the registry in :mod:`app.factcheck`."""
    return GoogleFactCheckClient(settings)
