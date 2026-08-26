"""Tavily — a search API built for retrieval rather than for browsing.

Verified against Tavily's own reference for ``POST /search`` (docs.tavily.com,
including its published OpenAPI schema). Where this module's behaviour depends on
something the reference does *not* state, the comment says so; there are two such
places and both are about dates.

Two things about Tavily shape the code more than the endpoint does.

**``content`` is not a snippet — it is up to three reranked chunks of the page,
joined with a literal** ``" [...] "``. That join is a gap in the text: the
characters on either side of it come from different parts of the document and were
never adjacent. A quote spanning it would read as continuous prose that nobody
wrote, which is why :data:`CHUNK_SEPARATOR` is documented here and why
:mod:`app.research.evidence` treats an elision as a hard boundary. The chunks are
kept joined rather than split into separate results because they are one page's
evidence, and splitting them would inflate the source count — the one number in a
dossier that must never be inflated.

**A date arrives only on ``topic="news"``.** ``published_date`` is absent from the
canonical ``/search`` reference and from the OpenAPI schema; it appears in the SDK
reference and in one tutorial's sample output, described there as news-only. So
``TAVILY_TOPIC`` defaults to ``general`` — the broad index, which is what
fact-checking wants, since primary documents, government pages and papers outrank
recency — and the cost of that default is stated plainly: most Tavily results will
carry no date at all. ``published_date`` is read whenever it is present regardless
of topic, so switching the setting to ``news`` needs no code change, and a result
without one is reported as undated rather than given a date.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.config import Settings
from app.core.errors import ConfigurationError, SearchError
from app.domain import DateBasis
from app.providers.dates import resolve
from app.providers.http import Http, ensure_parsed
from app.search.base import SearchResult

__all__ = ["CHUNK_SEPARATOR", "MAX_RESULTS", "TavilyClient", "build"]

#: What Tavily puts between chunks of one page's ``content``. Documented, exact,
#: and load-bearing: it marks a discontinuity in the text, so evidence selection
#: must never quote across it. See :mod:`app.research.evidence`.
CHUNK_SEPARATOR = " [...] "

#: Tavily's documented ceiling on ``max_results``.
MAX_RESULTS = 20


class TavilyClient(Http):
    """Searches the web through Tavily's ``/search`` endpoint."""

    name = "tavily"
    url = "https://api.tavily.com/search"
    error = SearchError

    def __init__(self, settings: Settings) -> None:
        if settings.TAVILY_API_KEY is None:
            raise ConfigurationError(
                "TAVILY_API_KEY is not set", details={"provider": self.name}
            )
        self._key = settings.TAVILY_API_KEY.get_secret_value()
        super().__init__(
            timeout=settings.SEARCH_TIMEOUT_SECONDS,
            attempts=settings.SEARCH_ATTEMPTS,
            secrets=(self._key,),
        )
        self._topic = str(settings.TAVILY_TOPIC)
        self._depth = str(settings.TAVILY_SEARCH_DEPTH)

    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        now: datetime,
    ) -> list[SearchResult]:
        """Results for ``query``, in Tavily's relevance order.

        ``include_answer`` and ``include_raw_content`` are both left off. The
        first returns a generated summary — a model's words *about* the sources
        rather than the sources, which is exactly what must not enter a dossier.
        The second returns whole page bodies, which is a great deal of bandwidth
        for text that evidence selection does not read.
        """
        payload = await self.fetch(
            "POST",
            self.url,
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "max_results": max(1, min(max_results, MAX_RESULTS)),
                "topic": self._topic,
                "search_depth": self._depth,
                "include_answer": False,
                "include_raw_content": False,
            },
        )
        return self.parse(payload, now=now)

    def parse(self, payload: Any, *, now: datetime) -> list[SearchResult]:
        """Turn a decoded response body into results.

        Public so that a test can exercise it against a recorded body without a
        network, which is the only way the parsing in here is verifiable at all.

        A malformed *envelope* raises rather than returning nothing: a schema
        change has to surface as a failure, because "Tavily now nests its results
        one level deeper" and "Tavily found nothing" would otherwise be
        indistinguishable — and the second is a legitimate answer this service
        reports to readers as fact.

        A malformed *item* is skipped. One result missing a URL is not evidence
        that the response is wrong, and discarding the other nineteen over it
        would lose real sources.
        """
        if not isinstance(payload, dict):
            raise SearchError(
                f"{self.name} returned {type(payload).__name__} where an object "
                "was expected",
                provider=self.name,
            )
        raw = payload.get("results")
        if not isinstance(raw, list):
            raise SearchError(
                f"{self.name} response has no 'results' array",
                provider=self.name,
                details={"keys": sorted(k for k in payload if isinstance(k, str))},
            )

        results: list[SearchResult] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url:
                continue
            published_at, basis, date_text = _date(
                item.get("published_date"), now=now
            )
            results.append(
                SearchResult(
                    url=url,
                    title=_text(item.get("title")),
                    # `content`, not `raw_content`: the chunk text exactly as it
                    # arrived, separators and all. Nothing is stripped, because
                    # evidence offsets index this string.
                    snippet=_text(item.get("content")),
                    score=_score(item.get("score")),
                    published_at=published_at,
                    date_basis=basis,
                    date_text=date_text,
                )
            )
        ensure_parsed(
            self.name, received=len(raw), parsed=len(results), error=self.error
        )
        return results


def _date(
    value: Any, *, now: datetime
) -> tuple[datetime | None, DateBasis | None, str | None]:
    """The date fields for one item: none, text-only, or resolved.

    ``published_date`` is Tavily's only date field, and there is deliberately no
    fallback to another timestamp on the item. A result without it has no date,
    and saying so is the point.

    An unparseable string yields ``date_text`` alone, with no ``published_at``.
    That combination is what a parser gap looks like from the outside: greppable,
    diagnosable, and honest about not having produced a date.
    """
    if not isinstance(value, str) or not value.strip():
        return None, None, None
    found = resolve(value, now=now, basis=DateBasis.PROVIDER)
    if found is None:
        return None, None, value
    published_at, basis = found
    return published_at, basis, value


def _text(value: Any) -> str:
    """A string field, or ``""`` when the provider omitted it.

    Never a placeholder. An empty title is an empty title; substituting the host
    or the URL would put words on the page that its publisher did not write.
    """
    return value if isinstance(value, str) else ""


def _score(value: Any) -> float | None:
    """Tavily's relevance score, when it is a number.

    ``bool`` is excluded explicitly because it is a subclass of ``int`` in Python,
    and ``True`` arriving here would otherwise become a relevance of 1.0 — the
    strongest score in the response, invented from a field that was not a number.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def build(settings: Settings) -> TavilyClient:
    """Factory for the registry in :mod:`app.search`."""
    return TavilyClient(settings)
