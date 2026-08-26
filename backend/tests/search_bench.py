"""A fake search provider, and the registry swap that installs one.

Shared by :mod:`tests.test_search_fanout`, which drives the fan-out directly, and
:mod:`tests.test_research_api`, which drives it through the endpoint. One fake for
both, because the two would otherwise disagree about what a provider is allowed to
do — and a fake that is more forgiving than the real client is how a test starts
passing for a reason the deployment does not share.

:func:`bench` is the load-bearing piece. The registry in :mod:`app.search` is a
module-level singleton, so a fake left registered after a test would make a later
test pass for the wrong reason: the hardest kind of failure to trace back. It puts
the real factories back unconditionally, restoring rather than unregistering, since
:mod:`app.search` registers all three at import and an emptied key would turn every
later provider lookup into a different error than the one under test.

Standard library and :mod:`app.search` only. No ``pytest`` import, so a subprocess
or an offline harness can build a fake without the test runner present.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from app.core.config import SearchProvider, Settings
from app.domain import DateBasis
from app.search import search_clients
from app.search.base import SearchClient, SearchResult
from app.search.brave import build as build_brave
from app.search.serper import build as build_serper
from app.search.tavily import build as build_tavily

#: The real factories, so :func:`bench` can restore exactly what it displaced.
REAL = {
    SearchProvider.TAVILY: build_tavily,
    SearchProvider.BRAVE: build_brave,
    SearchProvider.SERPER: build_serper,
}


class Fake:
    """A search client that answers from a script and records what it was asked."""

    def __init__(
        self,
        name: str,
        *,
        results: list[SearchResult] | None = None,
        error: Exception | None = None,
        fails: tuple[str, ...] = (),
    ) -> None:
        self.name = name
        self._results = results if results is not None else []
        self._error = error
        #: Queries that raise. Empty with ``error`` set means every query raises.
        self._fails = set(fails)
        self.queries: list[str] = []
        #: The instant each search was handed. ``app.services.research`` reads the
        #: clock once per request, and a test can only prove that by comparing what
        #: every provider was told against what the dossier reports.
        self.nows: list[datetime] = []
        self.closed = False

    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        now: datetime,
    ) -> list[SearchResult]:
        self.queries.append(query)
        self.nows.append(now)
        if self._error is not None and (not self._fails or query in self._fails):
            raise self._error
        return list(self._results)

    async def aclose(self) -> None:
        self.closed = True


def found(
    url: str,
    *,
    title: str = "T",
    snippet: str = "S",
    score: float | None = None,
    published_at: datetime | None = None,
    date_basis: DateBasis | None = None,
    date_text: str | None = None,
) -> SearchResult:
    """One result, with only the fields a test cares about spelled out."""
    return SearchResult(
        url=url,
        title=title,
        snippet=snippet,
        score=score,
        published_at=published_at,
        date_basis=date_basis,
        date_text=date_text,
    )


@contextmanager
def bench(fakes: dict[SearchProvider, Fake | Exception]) -> Iterator[None]:
    """Register ``fakes`` over the real providers for the duration of the block.

    An :class:`Exception` value stands for a provider whose *construction* fails —
    a missing key, a rejected setting — as opposed to one whose searches fail.
    """
    try:
        for provider, fake in fakes.items():
            search_clients.register(provider, _factory(fake))
        yield
    finally:
        for provider, build in REAL.items():
            search_clients.register(provider, build)


def _factory(fake: Fake | Exception) -> object:
    def build(_settings: Settings) -> SearchClient:
        if isinstance(fake, Exception):
            raise fake
        return fake  # type: ignore[return-value]

    return build
