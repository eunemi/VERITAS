"""The contract every web-search provider implements.

The seam is narrow on purpose: a provider's whole job is to turn a query string
into ordered results and to be honest about what it did not get. Everything
interesting — which pages are the same page, which publishers are independent,
which passage answers the claim — happens above it in :mod:`app.research`, over
results from every provider at once, and none of it belongs in a client that can
only see its own.

One rule governs every implementation. **A field is populated only when the
provider populated it.** No default titles, no host substituted for a missing
snippet, and above all no date that the provider did not report — see
:class:`~app.domain.research.DateBasis` for why a crawl timestamp is not a
publication date even though two of the three APIs hand one over on every result.
A missing value arrives as ``None`` and stays ``None`` all the way to the reader.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.domain import DateBasis


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One retrieved document.

    ``snippet`` is whatever text the provider returned with the result; it is not
    the page. Fetching the page is a separate, slower step, and a lot of triage
    can be done on the snippet alone.

    It is also the string that evidence quotes are sliced out of, which makes it
    the one field with a hard requirement attached: **it must be exactly the
    characters the provider sent.** A client that trimmed it, collapsed its
    whitespace or stripped markup out of it would shift every offset computed from
    it, and the verbatim guarantee in :class:`~app.domain.research.Evidence` would
    fail silently. Where a provider offers to decorate the snippet — Brave's
    ``text_decorations``, on by default, which injects highlight markers around
    query terms — the decoration is switched off at the request rather than
    cleaned up afterwards, so that there is nothing to clean.
    """

    url: str
    title: str
    snippet: str
    #: Provider-reported relevance, if any. Not comparable across providers.
    score: float | None = None
    #: Publication time, when the provider reports one — resolved from
    #: ``date_text`` by :mod:`app.providers.dates`. ``None`` whenever the provider
    #: said nothing, which for a general-topic Tavily search is every result.
    published_at: datetime | None = None
    #: What kind of date ``published_at`` is. ``None`` exactly when
    #: ``published_at`` is ``None``; the two are set together or not at all.
    date_basis: DateBasis | None = None
    #: The provider's own date string, verbatim, so a parse can be audited against
    #: what actually arrived. Set whenever the provider sent something, including
    #: when it could not be parsed — an unparseable date is still evidence about
    #: the source, and discarding it would hide a parser gap.
    date_text: str | None = None
    #: Host, for source-reputation scoring later.
    source: str | None = None


@runtime_checkable
class SearchClient(Protocol):
    """Searches the web.

    Implementations raise :class:`app.core.errors.SearchError` on failure. They do
    not return an empty list to signal a problem: "the index has nothing" and "the
    request did not happen" are different answers, and
    :class:`~app.domain.research.ProviderOutcome` can only tell them apart if the
    second one raises.
    """

    name: str

    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        now: datetime,
    ) -> list[SearchResult]:
        """Return results for ``query``, most relevant first.

        ``max_results`` is a ceiling, not a target. Every provider caps it (all
        three at 20) and each is free to return fewer, so a caller must never read
        the length of this list as a measure of anything but what came back.

        ``now`` is the instant dates are resolved against, and it is required
        rather than read from the clock inside the client. Brave returns ages as
        ``"2 days ago"``, which is not a date until something fixes the reference
        point; taking that point from the caller means every date in one dossier
        is relative to the same moment, the same response always parses to the
        same date, and a test can assert an exact value. Callers pass
        :attr:`~app.domain.research.Dossier.retrieved_at`.
        """
        ...

    async def aclose(self) -> None:
        """Release the underlying connection pool."""
        ...
