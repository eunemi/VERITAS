"""Assembly: dates, ordering, and the record of what was asked.

Three properties here decide whether the dossier can be trusted, and each is easier to
get wrong than to notice.

**The date.** Four bases arrive in one place — a stated publication date, one the
provider will not commit to, a relative age, and a date this service read out of a URL
path — and the temptation is to reduce them to a timestamp. The tests below pin the
opposite: the strongest basis wins wherever it arrived in the list,
:attr:`~app.domain.research.Source.date_basis` always says which it was, and
:attr:`~app.domain.research.Source.date_text` is empty exactly when no provider stated
a string to check the parse against.

**The ordering.** Strongest-evidence-first, with no interleaving by publisher. Making
the list *look* independent is a one-line change that misrepresents strength to flatter
a number, so there is a test that says the wire copy is allowed to fill the top places.

**The record.** ``queries`` is what was sent, stored verbatim. Rebuilding it here would
produce a list that stays plausible while quietly ceasing to be true — the first time
query construction changed under a cached result.

Nothing in this file asserts a source count, because there is no cap: how much gets
searched is the fan-out's decision, and a second limit at this layer would discard
retrieved evidence at the point furthest from anyone who could report the loss.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime

from app.domain.research import ClaimResearch, DateBasis, Retrieval
from app.research import dossier
from tests.research_bench import (
    NOW,
    WIRE,
    WIRE_TITLE,
    WIRE_TITLE_REGIONAL,
    WIRE_TITLE_REWRITTEN,
    WIRE_TRUNCATED,
    WIRE_WITH_LEAD,
    claim,
    retrieval,
)

RATE = claim(
    "The Bank of England held its benchmark rate at 4.75% in March 2026.",
    entities=(("Bank of England", "ORG"), ("March 2026", "DATE"), ("4.75%", "PERCENT")),
    keywords=(("benchmark rate", 1.0), ("inflation", 0.8)),
)

QUERIES = ("The Bank of England held its benchmark rate at 4.75% in March 2026.",)

MARCH = datetime(2026, 3, 12, 18, 0, tzinfo=UTC)
FEBRUARY = datetime(2026, 2, 2, 9, 0, tzinfo=UTC)


def build(*retrievals: Retrieval, now: datetime = NOW) -> ClaimResearch:
    """``for_claim`` with the arguments every test would otherwise repeat."""
    return dossier.for_claim(RATE, queries=QUERIES, retrievals=retrievals, now=now)


# ==================================================================== the date ====


def test_the_strongest_basis_wins_wherever_it_arrived() -> None:
    """Second in the list, and still chosen.

    A "first provider that has one" rule would make the date depend on which engine
    happened to answer first, so the same page would be dated differently on two
    requests. The weaker basis stays visible on its own retrieval.
    """
    found = build(
        retrieval(
            "brave",
            "https://bbc.co.uk/news/1",
            snippet=WIRE,
            published_at=FEBRUARY,
            date_basis=DateBasis.PROVIDER_MODIFIED,
            date_text="2026-02-02",
        ),
        retrieval(
            "tavily",
            "https://bbc.co.uk/news/1",
            snippet=WIRE,
            published_at=MARCH,
            date_basis=DateBasis.PROVIDER,
            date_text="2026-03-12T18:00:00Z",
        ),
    )
    source = found.sources[0]

    assert source.published_at == MARCH
    assert source.date_basis is DateBasis.PROVIDER
    assert source.date_text == "2026-03-12T18:00:00Z"
    # The one that lost is still in the record, so the disagreement is readable.
    assert FEBRUARY in {r.published_at for r in source.retrievals}


def test_every_basis_loses_to_every_stronger_one() -> None:
    """The whole ordering, not just the pair that happens to be tested elsewhere."""
    ordered = [
        DateBasis.PROVIDER,
        DateBasis.PROVIDER_MODIFIED,
        DateBasis.PROVIDER_RELATIVE,
        DateBasis.URL_PATH,
    ]

    assert ordered == sorted(ordered, key=lambda basis: dossier.BASIS_STRENGTH[basis])
    for stronger, weaker in itertools.combinations(ordered, 2):
        assert dossier.BASIS_STRENGTH[stronger] < dossier.BASIS_STRENGTH[weaker]


def test_a_relative_age_loses_to_a_stated_date() -> None:
    """``3 days ago`` only means something against the moment of retrieval."""
    found = build(
        retrieval(
            "brave",
            "https://bbc.co.uk/news/1",
            snippet=WIRE,
            published_at=FEBRUARY,
            date_basis=DateBasis.PROVIDER_RELATIVE,
            date_text="3 days ago",
        ),
        retrieval(
            "tavily",
            "https://bbc.co.uk/news/1",
            snippet=WIRE,
            published_at=MARCH,
            date_basis=DateBasis.PROVIDER,
            date_text="2026-03-12",
        ),
    )

    assert found.sources[0].date_basis is DateBasis.PROVIDER


def test_a_tie_within_one_basis_goes_to_the_earlier_retrieval() -> None:
    """Two providers, equal authority, different dates — a genuine coin-flip.

    Resolved by the ordering already established rather than by a new preference:
    picking the earlier or the later date would be this service inventing a date
    neither provider stated. Both remain on the retrievals.
    """
    found = build(
        retrieval(
            "tavily",
            "https://bbc.co.uk/news/1",
            snippet=WIRE,
            published_at=MARCH,
            date_basis=DateBasis.PROVIDER,
            date_text="2026-03-12",
        ),
        retrieval(
            "brave",
            "https://bbc.co.uk/news/1",
            snippet=WIRE,
            published_at=FEBRUARY,
            date_basis=DateBasis.PROVIDER,
            date_text="2026-02-02",
        ),
    )
    source = found.sources[0]

    assert source.published_at == MARCH
    assert source.date_text == "2026-03-12"
    assert {r.published_at for r in source.retrievals} == {MARCH, FEBRUARY}


def test_a_date_in_the_url_is_used_when_no_provider_stated_one() -> None:
    """The common path, not an edge case: Serper never dates, Tavily only for news."""
    found = build(
        retrieval("serper", "https://bbc.co.uk/news/2026/03/04/business-123", snippet=WIRE)
    )
    source = found.sources[0]

    assert source.published_at == datetime(2026, 3, 4, tzinfo=UTC)
    assert source.date_basis is DateBasis.URL_PATH


def test_a_url_date_carries_no_provider_string() -> None:
    """``date_text`` is where a reader checks a parse against what arrived.

    There is nothing to check this against. Putting the URL fragment there would
    present this service's own inference as something an engine reported.
    """
    found = build(
        retrieval("serper", "https://bbc.co.uk/news/2026/03/04/business-123", snippet=WIRE)
    )

    assert found.sources[0].date_text is None


def test_a_url_date_never_beats_a_provider_date() -> None:
    """Both are available here, and the path is the weakest basis there is."""
    found = build(
        retrieval(
            "tavily",
            "https://bbc.co.uk/news/2026/03/04/business-123",
            snippet=WIRE,
            published_at=MARCH,
            date_basis=DateBasis.PROVIDER,
            date_text="2026-03-12",
        )
    )

    assert found.sources[0].date_basis is DateBasis.PROVIDER
    assert found.sources[0].published_at == MARCH


def test_no_date_at_all_leaves_all_three_fields_empty() -> None:
    """"Unknown" is a state this has to be able to express.

    A fallback to the retrieval time would be a fabricated publication date that
    looks exactly like a real one, and every consumer downstream would believe it.
    """
    found = build(retrieval("serper", "https://bbc.co.uk/news/business-123", snippet=WIRE))
    source = found.sources[0]

    assert (source.published_at, source.date_basis, source.date_text) == (None, None, None)


def test_the_basis_is_set_exactly_when_the_date_is() -> None:
    """A date whose provenance is unrecorded cannot be quoted, so it must not exist."""
    found = build(
        retrieval("serper", "https://bbc.co.uk/news/a", snippet=WIRE),
        retrieval("serper", "https://bbc.co.uk/news/2026/03/04/b", snippet=WIRE),
        retrieval(
            "tavily",
            "https://bbc.co.uk/news/c",
            snippet=WIRE,
            published_at=MARCH,
            date_basis=DateBasis.PROVIDER,
            date_text="2026-03-12",
        ),
    )

    assert len(found.sources) == 3
    for source in found.sources:
        assert (source.published_at is None) == (source.date_basis is None)


def test_the_url_date_is_anchored_to_the_passed_instant() -> None:
    """``now`` is the dossier's ``retrieved_at``, not a fresh clock reading.

    Two sources in one dossier have to be dated against the same instant, or a
    request that straddles midnight dates half its sources to yesterday.
    """
    future = "https://bbc.co.uk/news/2027/01/01/business-123"

    assert build(retrieval("serper", future, snippet=WIRE)).sources[0].published_at is None
    later = build(
        retrieval("serper", future, snippet=WIRE),
        now=datetime(2027, 6, 1, tzinfo=UTC),
    )
    assert later.sources[0].published_at == datetime(2027, 1, 1, tzinfo=UTC)


# ================================================================== the record ====


def test_the_queries_are_recorded_verbatim_and_not_rebuilt() -> None:
    """Including a query the builder would never produce.

    Rebuilding would give a list that is plausible and untrue. The string below is
    what a caller sent; if ``queries`` were regenerated it would be replaced by the
    ladder for ``RATE`` and the record would stop matching the search.
    """
    sent = ("whatever the caller actually asked", "and a second thing")
    found = dossier.for_claim(
        RATE,
        queries=sent,
        retrievals=[retrieval("tavily", "https://bbc.co.uk/1", snippet=WIRE)],
        now=NOW,
    )

    assert found.queries == sent


def test_the_claim_recorded_is_the_text_that_was_searched() -> None:
    """The self-contained rewrite, since that is what the queries were built from."""
    assert build().claim == RATE.text


def test_nothing_found_is_an_empty_result_not_an_error() -> None:
    """Whether that means anything is ``Dossier.searched``'s job, one level up."""
    found = build()

    assert found.sources == ()
    assert found.queries == QUERIES
    assert found.stories == 0
    assert found.domains == ()


# ================================================================= the ordering ====


def test_sources_come_out_strongest_first() -> None:
    """By how well the evidence matches *this* claim, and nothing else."""
    found = build(
        retrieval(
            "tavily",
            "https://weak.example/1",
            snippet="The committee met on Thursday to discuss the outlook.",
            title="Committee meets",
        ),
        retrieval(
            "tavily",
            "https://strong.example/2",
            snippet="The Bank of England held its benchmark rate at 4.75% in March 2026.",
            title="Rates held",
        ),
    )
    scores = [
        source.evidence[0].score if source.evidence else -1.0 for source in found.sources
    ]

    assert found.sources[0].domain == "strong.example"
    assert scores == sorted(scores, reverse=True)


def test_a_source_with_no_matching_passage_sorts_last_and_stays() -> None:
    """That a page three engines returned says nothing about the claim is information.

    Dropping it would replace that with silence, and the dossier would look like the
    search found only relevant things.
    """
    found = build(
        retrieval(
            "tavily",
            "https://nothing.example/1",
            snippet="Ferry sailings from Portsmouth were cancelled in high winds.",
            title="Ferries cancelled",
        ),
        retrieval(
            "tavily",
            "https://something.example/2",
            snippet="The Bank of England held its benchmark rate at 4.75% in March 2026.",
            title="Rates held",
        ),
    )

    assert len(found.sources) == 2
    assert found.sources[-1].domain == "nothing.example"
    assert found.sources[-1].evidence == ()


def test_publishers_are_not_interleaved_to_look_independent() -> None:
    """One wire report may fill the top places, and here it does.

    Rotating publishers so the list looks diverse would misrepresent strength to
    flatter a number. The honest instrument is the cluster: these three share one, so
    ``stories`` says one story beside three domains.
    """
    found = build(
        retrieval("tavily", "https://reuters.com/a", title=WIRE_TITLE, snippet=WIRE),
        retrieval(
            "tavily",
            "https://apnews.com/b",
            title=WIRE_TITLE_REWRITTEN,
            snippet=WIRE_TRUNCATED,
        ),
        retrieval(
            "tavily",
            "https://heraldscotland.com/c",
            title=WIRE_TITLE_REGIONAL,
            snippet=WIRE_WITH_LEAD,
        ),
        retrieval(
            "tavily",
            "https://ft.com/d",
            title="Rate-setters hold firm",
            snippet=(
                "Rate-setters left borrowing costs untouched this month, "
                "disappointing mortgage holders who had hoped for relief."
            ),
        ),
    )

    assert found.stories == 2
    assert len(found.domains) == 4
    assert {source.cluster for source in found.sources[:3]} == {1}


def test_the_reference_numbers_are_assigned_after_ordering() -> None:
    """A ``ref`` that meant one page during construction and another in the output
    would be worse than no reference number at all."""
    found = build(
        retrieval(
            "tavily",
            "https://weak.example/1",
            snippet="The committee met on Thursday to discuss the outlook.",
        ),
        retrieval(
            "tavily",
            "https://strong.example/2",
            snippet="The Bank of England held its benchmark rate at 4.75% in March 2026.",
        ),
    )

    assert [source.ref for source in found.sources] == [1, 2]
    assert found.sources[0].domain == "strong.example"


def test_the_same_retrievals_always_produce_the_same_dossier() -> None:
    """Two ties broken by URL, so the order is total rather than incidental."""
    same = [
        retrieval("tavily", "https://b.example/1", snippet=WIRE, title=WIRE_TITLE),
        retrieval("brave", "https://a.example/2", snippet=WIRE, title=WIRE_TITLE),
        retrieval("serper", "https://c.example/3", snippet=WIRE, title=WIRE_TITLE),
    ]
    first = dossier.for_claim(RATE, queries=QUERIES, retrievals=same, now=NOW)
    second = dossier.for_claim(RATE, queries=QUERIES, retrievals=same, now=NOW)

    assert [s.url for s in first.sources] == [s.url for s in second.sources]
    assert first == second


def test_the_dossier_does_not_depend_on_the_order_providers_answered() -> None:
    """The fan-out emits in whatever order the network allowed.

    Every permutation of the same three retrievals of three different pages must give
    the same dossier — otherwise ``ref`` numbers and cluster ids shift between two
    requests that found exactly the same thing.
    """
    given = [
        retrieval("tavily", "https://reuters.com/a", title=WIRE_TITLE, snippet=WIRE),
        retrieval(
            "brave",
            "https://apnews.com/b",
            title=WIRE_TITLE_REWRITTEN,
            snippet=WIRE_TRUNCATED,
        ),
        retrieval(
            "serper",
            "https://ft.com/c",
            title="Rate-setters hold firm",
            snippet="Rate-setters left borrowing costs untouched at 4.75% this month.",
        ),
    ]
    shapes = {
        tuple(
            (source.url, source.ref, source.cluster)
            for source in dossier.for_claim(
                RATE,
                queries=QUERIES,
                retrievals=[given[index] for index in order],
                now=NOW,
            ).sources
        )
        for order in itertools.permutations(range(3))
    }

    assert len(shapes) == 1


# ================================================================ page identity ====


def test_one_page_from_three_engines_is_one_source() -> None:
    """And the corroboration between engines is recorded, not conflated with
    corroboration between publishers."""
    found = build(
        retrieval("tavily", "https://bbc.co.uk/news/1?utm_source=x", snippet=WIRE, rank=3),
        retrieval("brave", "http://www.bbc.co.uk/news/1/", snippet=WIRE, rank=1),
        retrieval("serper", "https://bbc.co.uk/news/1#top", snippet=WIRE, rank=7),
    )
    source = found.sources[0]

    assert len(found.sources) == 1
    assert source.providers == ("tavily", "brave", "serper")
    assert source.best_rank == 1
    assert len(source.urls) == 3
    assert found.stories == 1
    assert found.domains == ("bbc.co.uk",)


def test_evidence_offsets_index_the_snippet_they_name() -> None:
    """The end-to-end version of the guarantee, through the whole assembly.

    :meth:`~app.domain.research.Source.snippet_for` is the seam a reader uses to check
    a quote, and it has to return the string those offsets were measured against.
    """
    found = build(
        retrieval("tavily", "https://bbc.co.uk/news/1", snippet=WIRE),
        retrieval("brave", "https://bbc.co.uk/news/1", snippet=WIRE_TRUNCATED),
    )
    source = found.sources[0]

    assert source.evidence
    for evidence in source.evidence:
        snippet = source.snippet_for(evidence.provider)
        assert snippet is not None
        assert snippet[evidence.start : evidence.end] == evidence.quote


def test_a_source_always_has_at_least_one_retrieval() -> None:
    """A page with none would be one this service asserted the existence of."""
    found = build(
        retrieval("tavily", "https://bbc.co.uk/news/1", snippet=WIRE),
        retrieval("brave", "https://sky.com/news/2", snippet=WIRE_TRUNCATED),
    )

    assert found.sources
    for source in found.sources:
        assert source.retrievals


def test_the_evidence_limit_is_passed_through() -> None:
    """The one thing this layer does cap, and only because the caller asked."""
    snippet = " [...] ".join(
        [
            "The Bank of England held its benchmark rate at 4.75% in March 2026.",
            "Inflation kept the benchmark rate where it was in March 2026.",
            "The Bank of England put the 4.75% level beyond March 2026.",
        ]
    )
    found = dossier.for_claim(
        RATE,
        queries=QUERIES,
        retrievals=[retrieval("tavily", "https://bbc.co.uk/1", snippet=snippet)],
        now=NOW,
        evidence_limit=1,
    )

    assert len(found.sources[0].evidence) == 1
