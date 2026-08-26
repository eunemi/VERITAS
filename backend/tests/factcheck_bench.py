"""A fake fact-check database, and the registry swap that installs one.

The counterpart to :mod:`tests.search_bench`, and shared for the same reason: one fake
serves :mod:`tests.test_factcheck_lookup`, which drives the lookup directly,
:mod:`tests.test_research_service`, which drives it through the service, and
:mod:`tests.test_research_api`, which drives it through the endpoint. A second, more
forgiving fake in one of them is how a test starts passing for a reason the deployment
does not share.

:func:`bench` is the load-bearing piece. The registry in :mod:`app.factcheck` is a
module-level singleton, so a fake left registered after a test would make a later test
pass for the wrong reason — the hardest kind of failure to trace back. It restores the
real factory unconditionally rather than unregistering, since :mod:`app.factcheck`
registers Google at import and an emptied key would turn every later lookup into a
different error than the one under test.

Standard library and :mod:`app.factcheck` only. No ``pytest`` import, so a subprocess or
an offline harness can build a fake without the test runner present.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from app.core.config import FactCheckProvider, Settings
from app.domain import Review, ReviewedClaim
from app.factcheck import fact_check_clients
from app.factcheck.base import FactCheckClient
from app.factcheck.google import build as build_google

#: The real factories, so :func:`bench` can restore exactly what it displaced.
REAL = {FactCheckProvider.GOOGLE: build_google}


class Fake:
    """A fact-check client that answers from a script and records what it was asked."""

    def __init__(
        self,
        name: str = "google",
        *,
        found: dict[str, list[ReviewedClaim]] | None = None,
        results: list[ReviewedClaim] | None = None,
        error: Exception | None = None,
        fails: tuple[str, ...] = (),
    ) -> None:
        self.name = name
        #: Per-query answers, for a test that needs two claims to get different records.
        self._found = found or {}
        #: The answer for any query not in ``found``.
        self._results = results if results is not None else []
        self._error = error
        #: Queries that raise. Empty with ``error`` set means every query raises.
        self._fails = set(fails)
        self.queries: list[str] = []
        #: What each lookup was told about paging and filtering, so a test can prove the
        #: settings reach the wire rather than trusting that they do.
        self.limits: list[int] = []
        self.languages: list[str] = []
        self.ages: list[int] = []
        #: The instant each lookup was handed. ``app.services.research`` reads the clock
        #: once per request, and the only way to prove that is to compare what every
        #: provider — search and fact check alike — was told against the dossier.
        self.nows: list[datetime] = []
        self.closed = False

    async def lookup(
        self,
        query: str,
        *,
        max_results: int = 10,
        language: str = "",
        max_age_days: int = 0,
        now: datetime,
    ) -> list[ReviewedClaim]:
        self.queries.append(query)
        self.limits.append(max_results)
        self.languages.append(language)
        self.ages.append(max_age_days)
        self.nows.append(now)
        if self._error is not None and (not self._fails or query in self._fails):
            raise self._error
        if query in self._found:
            return list(self._found[query])
        return list(self._results)

    async def aclose(self) -> None:
        self.closed = True


def review(
    *,
    publisher: str = "Example Fact Check",
    site: str = "example.org",
    url: str = "https://example.org/review",
    rating: str = "False",
    title: str = "",
    language: str = "",
    reviewed_at: datetime | None = None,
    date_text: str | None = None,
) -> Review:
    """One review, with only the fields a test cares about spelled out.

    ``stance`` and ``stance_from`` are deliberately not parameters. They are filled in by
    :func:`app.research.reviews.select`, and a test that could preset them could assert a
    stance the vocabulary table never produced.
    """
    return Review(
        publisher=publisher,
        site=site,
        url=url,
        rating=rating,
        title=title,
        language=language,
        reviewed_at=reviewed_at,
        date_text=date_text,
    )


def record(
    text: str,
    *reviews: Review,
    claimant: str = "",
    claimed_at: datetime | None = None,
    date_text: str | None = None,
) -> ReviewedClaim:
    """One database record. Defaults to a single ``False`` review when none is given."""
    return ReviewedClaim(
        text=text,
        reviews=reviews or (review(),),
        claimant=claimant,
        claimed_at=claimed_at,
        date_text=date_text,
    )


@contextmanager
def bench(fake: Fake | Exception) -> Iterator[None]:
    """Register ``fake`` over the real database for the duration of the block.

    An :class:`Exception` value stands for a database whose *construction* fails — a
    missing key, a rejected setting — as opposed to one whose lookups fail. Both paths
    matter and they produce different outcomes: the first is ``skipped``, the second
    ``failed``.
    """
    try:
        fact_check_clients.register(FactCheckProvider.GOOGLE, _factory(fake))
        yield
    finally:
        for provider, build in REAL.items():
            fact_check_clients.register(provider, build)


def _factory(fake: Fake | Exception) -> object:
    def build(_settings: Settings) -> FactCheckClient:
        if isinstance(fake, Exception):
            raise fake
        return fake  # type: ignore[return-value]

    return build
