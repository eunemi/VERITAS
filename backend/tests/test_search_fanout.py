"""Fan-out behaviour: isolation between providers, and honest outcomes.

The rule under test is the one in :mod:`app.search.fanout`'s docstring: **a
provider's failure must cost the dossier that provider's results and nothing else.**
Almost every test here is a variation on it — one provider dies and the others must
be unaffected, one query in a batch dies and the rest must survive with the
shortfall reported rather than hidden.

The fakes are registered over the real providers through the registry, which allows
replacement precisely so that a test need not touch a private attribute.
:func:`tests.search_bench.bench` puts the real factories back afterwards: the registry
in :mod:`app.search` is a module-level singleton, so a fake left behind would make a
later test pass for the wrong reason.

The fake itself lives in :mod:`tests.search_bench` because
:mod:`tests.test_research_api` drives the same fan-out through the endpoint, and two
fakes would eventually disagree about what a provider may do.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import SearchProvider, Settings
from app.core.errors import SearchError
from app.domain import ProviderStatus
from app.search.fanout import Task, harvest
from tests.search_bench import Fake, bench, found

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


def configured(*providers: SearchProvider, **overrides: object) -> Settings:
    return Settings(_env_file=None, SEARCH_PROVIDERS=list(providers), **overrides)


# ---------------------------------------------------------------- isolation ----


async def test_a_provider_failure_costs_only_its_own_results() -> None:
    """The central promise. One dead engine, two live results."""
    dead = Fake("tavily", error=SearchError("tavily is down", provider="tavily"))
    alive = Fake(
        "brave", results=[found("https://a.example/1"), found("https://b.example/2")]
    )

    with bench({SearchProvider.TAVILY: dead, SearchProvider.BRAVE: alive}):
        result = await harvest(
            [Task(claim="c", queries=("q",))],
            settings=configured(SearchProvider.TAVILY, SearchProvider.BRAVE),
            now=NOW,
        )

    assert [r.url for r in result.retrievals[0]] == [
        "https://a.example/1",
        "https://b.example/2",
    ]
    outcomes = {o.provider: o for o in result.outcomes}
    assert outcomes["tavily"].status is ProviderStatus.FAILED
    assert outcomes["brave"].status is ProviderStatus.SEARCHED
    assert outcomes["brave"].results == 2


async def test_a_missing_key_is_skipped_with_a_reason() -> None:
    """A one-key deployment must be legible, not mysterious.

    No fakes here: the real factories run, and every one of them raises
    ``ConfigurationError`` because no key is set.
    """
    result = await harvest(
        [Task(claim="c", queries=("q",)), Task(claim="d", queries=("r",))],
        settings=configured(
            SearchProvider.TAVILY, SearchProvider.BRAVE, SearchProvider.SERPER
        ),
        now=NOW,
    )

    assert [o.status for o in result.outcomes] == [ProviderStatus.SKIPPED] * 3
    assert all("API_KEY" in o.detail for o in result.outcomes)
    # Aligned with the tasks even though nothing ran, so a caller can index safely.
    assert result.retrievals == ((), ())


async def test_every_client_is_closed_even_after_a_failure() -> None:
    dead = Fake("tavily", error=SearchError("down", provider="tavily"))
    alive = Fake("brave", results=[found("https://a.example/1")])

    with bench({SearchProvider.TAVILY: dead, SearchProvider.BRAVE: alive}):
        await harvest(
            [Task(claim="c", queries=("q",))],
            settings=configured(SearchProvider.TAVILY, SearchProvider.BRAVE),
            now=NOW,
        )

    assert dead.closed
    assert alive.closed


async def test_a_repeated_provider_is_searched_once() -> None:
    """``SEARCH_PROVIDERS=tavily,tavily`` must not make one engine look like two."""
    fake = Fake("tavily", results=[found("https://a.example/1")])

    with bench({SearchProvider.TAVILY: fake}):
        result = await harvest(
            [Task(claim="c", queries=("q",))],
            settings=configured(SearchProvider.TAVILY, SearchProvider.TAVILY),
            now=NOW,
        )

    assert len(result.outcomes) == 1
    assert fake.queries == ["q"]
    assert len(result.retrievals[0]) == 1


# ----------------------------------------------------------------- outcomes ----


async def test_zero_results_is_searched_not_failed() -> None:
    """An index that returned nothing is a finding, and a reportable one."""
    empty = Fake("tavily", results=[])

    with bench({SearchProvider.TAVILY: empty}):
        result = await harvest(
            [Task(claim="c", queries=("q",))],
            settings=configured(SearchProvider.TAVILY),
            now=NOW,
        )

    (outcome,) = result.outcomes
    assert outcome.status is ProviderStatus.SEARCHED
    assert outcome.results == 0
    assert result.retrievals[0] == ()


async def test_some_queries_failing_is_partial() -> None:
    """Neither SEARCHED nor FAILED would be true, so there is a third state.

    A rate limit that kills half a batch has made the dossier thinner in a way no
    reader could otherwise detect. The results are kept *and* the gap is stated.
    """
    flaky = Fake(
        "tavily",
        results=[found("https://a.example/1")],
        error=SearchError("rate limited", provider="tavily"),
        fails=("second",),
    )

    with bench({SearchProvider.TAVILY: flaky}):
        result = await harvest(
            [Task(claim="c", queries=("first", "second"))],
            settings=configured(SearchProvider.TAVILY),
            now=NOW,
        )

    (outcome,) = result.outcomes
    assert outcome.status is ProviderStatus.PARTIAL
    assert outcome.results == 1
    assert "1 of 2 queries failed" in outcome.detail
    assert "rate limited" in outcome.detail
    # The one query that worked still contributed its source.
    assert len(result.retrievals[0]) == 1


async def test_outcomes_record_the_queries_that_ran() -> None:
    fake = Fake("tavily", results=[])

    with bench({SearchProvider.TAVILY: fake}):
        result = await harvest(
            [
                Task(claim="c", queries=("alpha", "beta")),
                Task(claim="d", queries=("gamma",)),
            ],
            settings=configured(SearchProvider.TAVILY),
            now=NOW,
        )

    (outcome,) = result.outcomes
    assert sorted(outcome.queries) == ["alpha", "beta", "gamma"]


async def test_outcomes_are_ordered_deterministically() -> None:
    fakes = {
        SearchProvider.SERPER: Fake("serper", results=[]),
        SearchProvider.BRAVE: Fake("brave", results=[]),
        SearchProvider.TAVILY: Fake("tavily", results=[]),
    }

    with bench(dict(fakes)):
        result = await harvest(
            [Task(claim="c", queries=("q",))],
            settings=configured(
                SearchProvider.SERPER, SearchProvider.BRAVE, SearchProvider.TAVILY
            ),
            now=NOW,
        )

    assert [o.provider for o in result.outcomes] == ["brave", "serper", "tavily"]


async def test_a_provider_that_cannot_be_built_is_reported_not_raised() -> None:
    """A broken constructor is one provider's problem, not the request's."""
    alive = Fake("brave", results=[found("https://a.example/1")])

    with bench(
        {
            SearchProvider.TAVILY: SearchError("bad setting", provider="tavily"),
            SearchProvider.BRAVE: alive,
        }
    ):
        result = await harvest(
            [Task(claim="c", queries=("q",))],
            settings=configured(SearchProvider.TAVILY, SearchProvider.BRAVE),
            now=NOW,
        )

    outcomes = {o.provider: o for o in result.outcomes}
    assert outcomes["tavily"].status is ProviderStatus.FAILED
    assert len(result.retrievals[0]) == 1


async def test_a_key_never_reaches_an_outcome_detail() -> None:
    """Provider messages quote the request; this detail is returned to a client."""
    key = "tvly-secret-key-value"
    leaky = Fake(
        "tavily", error=SearchError(f"token {key} rejected", provider="tavily")
    )

    with bench({SearchProvider.TAVILY: leaky}):
        result = await harvest(
            [Task(claim="c", queries=("q",))],
            settings=configured(SearchProvider.TAVILY, TAVILY_API_KEY=key),
            now=NOW,
        )

    (outcome,) = result.outcomes
    assert key not in outcome.detail
    assert "***" in outcome.detail


# --------------------------------------------------------------- retrievals ----


async def test_retrievals_stay_aligned_with_their_task() -> None:
    """Index *i* holds what was found for task *i*, even for identical claims."""

    class ByQuery(Fake):
        async def search(
            self, query: str, *, max_results: int = 10, now: datetime
        ) -> list[SearchResult]:
            self.queries.append(query)
            return [found(f"https://example.com/{query}")]

    with bench({SearchProvider.TAVILY: ByQuery("tavily")}):
        result = await harvest(
            [
                Task(claim="same", queries=("first",)),
                Task(claim="same", queries=("second",)),
            ],
            settings=configured(SearchProvider.TAVILY),
            now=NOW,
        )

    assert [r.url for r in result.retrievals[0]] == ["https://example.com/first"]
    assert [r.url for r in result.retrievals[1]] == ["https://example.com/second"]


async def test_rank_restarts_at_one_for_each_query() -> None:
    """Rank is a position within one provider's answer to one query.

    Continuing the count across queries would make the fourth result of the second
    query look less relevant than the first result of the first, which is a
    comparison neither provider offered.
    """
    fake = Fake(
        "tavily",
        results=[found("https://a.example/1"), found("https://b.example/2")],
    )

    with bench({SearchProvider.TAVILY: fake}):
        result = await harvest(
            [Task(claim="c", queries=("first", "second"))],
            settings=configured(SearchProvider.TAVILY),
            now=NOW,
        )

    assert [r.rank for r in result.retrievals[0]] == [1, 2, 1, 2]


async def test_every_retrieval_records_its_provider_and_query() -> None:
    """The audit trail: which engine said this, and what was it asked."""
    fake = Fake("tavily", results=[found("https://a.example/1")])

    with bench({SearchProvider.TAVILY: fake}):
        result = await harvest(
            [Task(claim="c", queries=("who won",))],
            settings=configured(SearchProvider.TAVILY),
            now=NOW,
        )

    (retrieval,) = result.retrievals[0]
    assert retrieval.provider == "tavily"
    assert retrieval.query == "who won"


async def test_no_tasks_is_no_work_and_no_error() -> None:
    fake = Fake("tavily", results=[found("https://a.example/1")])

    with bench({SearchProvider.TAVILY: fake}):
        result = await harvest([], settings=configured(SearchProvider.TAVILY), now=NOW)

    assert result.retrievals == ()
    assert fake.queries == []
    assert result.outcomes[0].status is ProviderStatus.SEARCHED
