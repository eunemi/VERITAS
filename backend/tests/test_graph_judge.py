"""The judge, and the one thing it must be willing to say.

Every test here is about a single property: **``UNCERTAIN`` is a verdict, not a low
score.** A system that only ever answers on a scale from true to false has no way to
report that it could not find out, and the failure that follows is not a wrong number —
it is a confident-looking answer assembled from one source, or from none.

So the judge runs a **sufficiency gate before it weighs anything**, and the first
section below is one test per way through it: nothing searched, nothing found, nothing
that stood up, not enough that were independent, and nothing that pointed either way.
The five are deliberately distinguished. "No provider was configured" and "three
engines found nothing" produce an identical empty source list and mean opposite things,
and :attr:`~app.graph.verdict.ClaimRuling.insufficiency` is where the difference is
recorded.

The second section is the weighing, and the third is the artifact-level roll-up, whose
rule is that the worst finding carries: one refuted claim among four supported ones is
not a mostly-true artifact.

Runs with no LangGraph installed. The judge is called with a dict — see
:mod:`tests.graph_bench`.
"""

from __future__ import annotations

import pytest

from app.domain import Determination
from app.graph.agents.judge import (
    SETTLED_UNCERTAINTY,
    UNGROUNDED_UNCERTAINTY,
    JudgeAgent,
)
from app.graph.state import GraphState
from app.graph.verdict import (
    Bearing,
    Indication,
    Judgement,
    Ruling,
    Thresholds,
    as_determination,
)
from tests import graph_bench
from tests.graph_bench import CLAIM, RIVAL, rated, reported


async def rule(state: GraphState, **limits: object) -> Ruling:
    """Run the judge over ``state`` and return the ruling it wrote."""
    agent = JudgeAgent(thresholds=Thresholds(**limits)) if limits else JudgeAgent()
    written = await agent(state)
    ruling = written["ruling"]
    assert ruling is not None
    return ruling


# --------------------------------------------------------- the gate ----


async def test_no_claims_is_uncertain_and_not_a_verdict() -> None:
    """An artifact nothing checkable was found in is unresolved, never supported.

    The empty-input case, and the one a rating system gets wrong most cheaply: with no
    claims there is nothing to refute, so anything that scores absence of refutation as
    support reports a blank page as true.
    """
    ruling = await rule(
        GraphState(now=graph_bench.NOW, claims=(), providers=(), ruling=None, trace=())
    )
    assert ruling.judgement is Judgement.UNCERTAIN
    assert ruling.confidence == UNGROUNDED_UNCERTAINTY
    assert not ruling.claims


async def test_a_failed_provider_is_not_reported_as_finding_nothing() -> None:
    """No provider answered, so the emptiness is about this deployment."""
    ruling = await rule(
        graph_bench.state((), providers=(graph_bench.outcome(answered=False),))
    )
    (claim,) = ruling.claims
    assert claim.judgement is Judgement.UNCERTAIN
    assert "no search provider answered" in claim.insufficiency
    assert claim.confidence == UNGROUNDED_UNCERTAINTY


async def test_searching_and_finding_nothing_says_so_instead() -> None:
    """The same empty source list, the opposite explanation — and a firmer holding.

    The pair of this test and the one above it is the whole point of reading
    :attr:`~app.domain.ProviderOutcome.status` rather than counting results.
    """
    ruling = await rule(graph_bench.state(()))
    (claim,) = ruling.claims
    assert claim.judgement is Judgement.UNCERTAIN
    assert "returned no sources" in claim.insufficiency
    assert claim.confidence == SETTLED_UNCERTAINTY


async def test_one_source_is_not_corroboration() -> None:
    """Below ``min_sources``, however good the single source is."""
    ruling = await rule(graph_bench.state((reported("https://reuters.com/a"),)))
    (claim,) = ruling.claims
    assert claim.judgement is Judgement.UNCERTAIN
    assert "1 independent source(s)" in claim.insufficiency


async def test_three_copies_of_one_wire_story_count_as_one() -> None:
    """Syndication cannot manufacture the corroboration the gate requires.

    The sharpest case in this file. Three real publishers, three real pages, three real
    passages carrying the claim's figure — and one newsroom behind all of them, which
    the dossier already recorded as a shared cluster. A judge that counted pages would
    call this claim supported by three sources, and be wrong in the direction that
    matters: a wire story repeated is a story that was easy to find, not one that was
    independently established.
    """
    syndicated = tuple(
        reported(url, ref=ref, cluster=7)
        for ref, url in enumerate(
            (
                "https://reuters.com/a",
                "https://abc.net.au/b",
                "https://thestar.com.my/c",
            ),
            start=1,
        )
    )
    ruling = await rule(graph_bench.state(syndicated))
    (claim,) = ruling.claims
    assert claim.judgement is Judgement.UNCERTAIN
    assert "1 independent source(s)" in claim.insufficiency


async def test_two_pages_from_one_publisher_count_as_one() -> None:
    """Independence is counted over publishers, not URLs."""
    same = (
        reported("https://reuters.com/a", ref=1),
        reported("https://reuters.com/b", ref=2),
    )
    ruling = await rule(graph_bench.state(same))
    (claim,) = ruling.claims
    assert claim.judgement is Judgement.UNCERTAIN
    assert "1 independent source(s)" in claim.insufficiency


async def test_a_source_with_no_passage_does_not_count() -> None:
    """A page found is not a page that bore on the claim."""
    ruling = await rule(
        graph_bench.state(
            (
                reported("https://reuters.com/a", ref=1),
                reported("https://theguardian.com/b", "", ref=2),
            )
        )
    )
    (claim,) = ruling.claims
    assert claim.judgement is Judgement.UNCERTAIN
    assert "1 independent source(s)" in claim.insufficiency


async def test_sources_that_bear_on_a_claim_without_settling_it_are_uncertain() -> None:
    """The gate passes, the weighing finds nothing directional, and it holds.

    Two independent sources are about the claim's subject and neither repeats its
    figure or its entities. That is the commonest real outcome and the one with no place
    on a truth scale: sharing a topic is not confirming an assertion.
    """
    vague = (
        reported("https://reuters.com/a", ref=1, matched=()),
        reported("https://theguardian.com/b", ref=2, matched=()),
    )
    ruling = await rule(graph_bench.state(vague))
    (claim,) = ruling.claims
    assert claim.judgement is Judgement.UNCERTAIN
    assert "none of them settles it" in claim.insufficiency
    assert claim.support == 0.0
    assert claim.refute == 0.0


async def test_ungraded_sources_still_reach_the_judge() -> None:
    """``CREDIBILITY_ENABLED=False`` must not silently decide every verdict.

    With grading off there is no standing to compare against the floor, and a gate that
    treated a missing grade as a failing one would turn one configuration flag into a
    blanket ``UNCERTAIN`` on everything.
    """
    pair = (
        reported("https://reuters.com/a", ref=1),
        reported("https://theguardian.com/b", ref=2),
    )
    ruling = await rule(graph_bench.state(pair, grade=False))
    (claim,) = ruling.claims
    assert claim.judgement is Judgement.SUPPORTED


async def test_insufficiency_is_populated_exactly_when_uncertain() -> None:
    """The contract on the field, across every case this module builds.

    Stated as an invariant rather than checked case by case, because the field's only
    value is that a reader can rely on it: an ``UNCERTAIN`` with an empty reason is
    indistinguishable from a shrug.
    """
    pair = (
        reported("https://reuters.com/a", ref=1),
        reported("https://theguardian.com/b", ref=2),
    )
    for state in (
        graph_bench.state(()),
        graph_bench.state((reported("https://reuters.com/a"),)),
        graph_bench.state(pair),
        graph_bench.state(pair, providers=(graph_bench.outcome(answered=False),)),
    ):
        for claim in (await rule(state)).claims:
            assert bool(claim.insufficiency) == (
                claim.judgement is Judgement.UNCERTAIN
            ), claim


# ------------------------------------------------------ the weighing ----


async def test_two_independent_sources_repeating_the_figure_support_the_claim() -> None:
    pair = (
        reported("https://reuters.com/a", ref=1),
        reported("https://theguardian.com/b", ref=2),
    )
    ruling = await rule(graph_bench.state(pair))
    (claim,) = ruling.claims
    assert claim.judgement is Judgement.SUPPORTED
    assert claim.support > claim.refute
    assert claim.refute == 0.0
    assert len(claim.indications) == 2


async def test_a_unanimous_false_rating_refutes() -> None:
    pair = (
        reported("https://reuters.com/a", ref=1, matched=()),
        reported("https://theguardian.com/b", ref=2, matched=()),
    )
    ruling = await rule(graph_bench.state(pair, fact_checks=rated("False", "Fake")))
    (claim,) = ruling.claims
    assert claim.judgement is Judgement.REFUTED
    assert claim.refute > claim.support


async def test_reviewers_who_disagreed_are_not_read_as_agreement() -> None:
    """A split is the contradiction agent's finding, and the judge adds nothing.

    Two reviewers, opposite ratings. ``FactCheck.agreement`` is ``None``, so nothing
    directional comes from the review here — weighing it in both places would count one
    disagreement twice.
    """
    pair = (
        reported("https://reuters.com/a", ref=1, matched=()),
        reported("https://theguardian.com/b", ref=2, matched=()),
    )
    ruling = await rule(graph_bench.state(pair, fact_checks=rated("True", "False")))
    (claim,) = ruling.claims
    assert claim.judgement is Judgement.UNCERTAIN
    assert not claim.indications


async def test_reviewers_who_could_not_settle_it_add_no_weight() -> None:
    """A rating of "Mixture" is not evidence that the claim is half true.

    ``STANCE_WEIGHTS`` omits ``MIXED``, and this is the test that says so: a reviewer
    who declined to come down found what this service found.
    """
    pair = (
        reported("https://reuters.com/a", ref=1, matched=()),
        reported("https://theguardian.com/b", ref=2, matched=()),
    )
    ruling = await rule(graph_bench.state(pair, fact_checks=rated("Mixture")))
    (claim,) = ruling.claims
    assert claim.judgement is Judgement.UNCERTAIN
    assert not claim.indications


async def test_a_contradiction_against_corroboration_reads_as_contested() -> None:
    """Both sides substantial, so neither is reported alone."""
    pair = (
        reported("https://reuters.com/a", ref=1),
        reported("https://theguardian.com/b", RIVAL, ref=2, matched=()),
    )
    conflict = Indication(
        agent="contradiction",
        bearing=Bearing.REFUTES,
        weight=0.8,
        detail="theguardian.com carries 5.25% where the claim states 4.75%",
    )
    ruling = await rule(graph_bench.state(pair, conflicts=(conflict,)))
    (claim,) = ruling.claims
    assert claim.judgement is Judgement.MIXED
    assert claim.support > 0
    assert claim.refute > 0


async def test_a_confidence_never_reads_as_settled_fact() -> None:
    """Capped, whatever the arithmetic produces.

    Everything the graph weighs is a search snippet or somebody else's rating. A
    one-sided result from good sources is the strongest thing it can see, and it is
    still not grounds for a number that prints as certainty.
    """
    pair = (
        reported("https://reuters.com/a", ref=1),
        reported("https://theguardian.com/b", ref=2),
    )
    ruling = await rule(graph_bench.state(pair))
    (claim,) = ruling.claims
    assert claim.confidence <= 0.9
    assert ruling.confidence <= 0.9


# --------------------------------------------------- the whole artifact ----


async def test_one_refuted_claim_carries_the_artifact() -> None:
    """Not averaged. A reader needs the refutation to survive the summary."""
    supported = (
        reported("https://reuters.com/a", ref=1),
        reported("https://theguardian.com/b", ref=2),
    )
    two = graph_bench.state(supported)
    two["claims"] = (
        graph_bench.claim(CLAIM, ref=1),
        graph_bench.claim("Unemployment fell to 3.9% in February 2026.", ref=2),
    )
    two["research"] = (
        two["research"][0],
        two["research"][0],
    )
    two["grading"] = (two["grading"][0], two["grading"][0])
    two["conflicts"] = (
        (),
        (
            Indication(
                agent="contradiction",
                bearing=Bearing.REFUTES,
                weight=1.0,
                detail="the record states 4.1%",
            ),
        ),
    )
    ruling = await rule(two)
    assert [c.judgement for c in ruling.claims] == [
        Judgement.SUPPORTED,
        Judgement.MIXED,
    ]
    assert ruling.judgement is Judgement.MIXED
    assert "1 mixed" in ruling.rationale


@pytest.mark.parametrize(
    ("judgement", "determination"),
    [
        (Judgement.SUPPORTED, Determination.SUPPORTED),
        (Judgement.REFUTED, Determination.CONTRADICTED),
        (Judgement.MIXED, Determination.CONTESTED),
        (Judgement.UNCERTAIN, Determination.INSUFFICIENT),
    ],
)
def test_every_judgement_reaches_the_wire(
    judgement: Judgement, determination: Determination
) -> None:
    """``UNCERTAIN`` is the load-bearing row.

    ``Determination`` has no ``UNCERTAIN`` member — it is pinned to the strings
    ``src/lib/types/agents.ts`` publishes — and ``toneOf`` there classifies anything it
    does not recognise as adverse. Adding one would render an unresolved claim as though
    it had been found false, so it maps to ``INSUFFICIENT``, which that file's
    ``OPEN_SET`` already reads as open.
    """
    assert as_determination(judgement) is determination
