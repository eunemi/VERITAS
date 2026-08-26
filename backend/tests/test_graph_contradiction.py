"""The contradiction agent: three mechanical checks, and what each is worth.

There is no stance model in this service, so this agent cannot read a passage's
argument. It reads three things that can be checked against the claim without one — a
rival figure, a negation, and reviewers who disagreed with each other — and the tests
here are as much about the **limits** of each as about its behaviour.

That is why two of them assert a conflict is *not* raised. A figure detector that fires
on "rates held at 4.75%, down from 5.25%" would report every piece of context as a
dispute, and a negation detector comparing a percentage with a year would report every
passage that mentions both. Those two false positives are the ones this agent would
produce constantly if the guards were dropped, and neither would look like a bug in a
verdict — it would look like a source that disagreed.

The division of labour with the judge is the other property under test. The judge weighs
:attr:`~app.domain.FactCheck.agreement`, which is only set when every reviewer said the
same thing; this agent takes the case where they split. Neither reads the other's, so no
review is weighed twice.

Runs with no LangGraph installed.
"""

from __future__ import annotations

from app.domain import ClaimResearch
from app.graph.agents.contradiction import ContradictionAgent
from app.graph.state import GraphState
from app.graph.verdict import (
    FIGURE_CONFLICT_WEIGHT,
    NEGATION_CONFLICT_WEIGHT,
    REVIEWER_SPLIT_WEIGHT,
    Bearing,
)
from tests.graph_bench import CLAIM, MATCHING, RIVAL, rated, reported

#: A claim whose only figure is a percentage, for the comparability guard.
RATE_ONLY = "The unemployment rate stands at 3.9%."


async def against(*sources: object, text: str = CLAIM, checks: tuple = ()) -> tuple:
    """Run the agent over one claim and return the indications it produced."""
    record = ClaimResearch(
        claim=text,
        queries=("q",),
        sources=tuple(sources),  # type: ignore[arg-type]
        fact_checks=checks,
    )
    written = await ContradictionAgent()(GraphState(research=(record,)))
    (found,) = written["conflicts"]
    return found


async def test_a_rival_figure_is_a_conflict() -> None:
    found = await against(reported("https://theguardian.com/b", RIVAL, matched=()))
    (indication,) = found
    assert indication.bearing is Bearing.REFUTES
    assert indication.weight == FIGURE_CONFLICT_WEIGHT
    assert "5.25%" in indication.detail
    assert "4.75%" in indication.detail


async def test_a_passage_carrying_both_figures_is_context_and_not_a_conflict() -> None:
    """"Held at 4.75%, down from 5.25%" elaborates on the claim; it does not dispute it.

    The guard this test protects is the difference between an agent that finds
    disagreement and one that flags every source giving background.
    """
    both = (
        "The central bank held its policy rate at 4.75% in February, down from 5.25% "
        "at the start of the tightening cycle."
    )
    assert await against(reported("https://reuters.com/a", both)) == ()


async def test_a_negation_beside_the_claims_own_figure_is_a_weaker_conflict() -> None:
    """Detected, and weighted below a figure conflict because it is noisy.

    "Critics said 4.75% was not enough" trips this, and that is a known cost of a
    detector with no parse behind it — which is why the weight is what it is and why
    :data:`~app.graph.verdict.NEGATION_CONFLICT_WEIGHT` alone cannot carry a claim past
    the judge's gate.
    """
    denial = (
        "The central bank did not hold its policy rate at 4.75% in February, "
        "contrary to reports circulating this week."
    )
    (indication,) = await against(reported("https://reuters.com/a", denial))
    assert indication.weight == NEGATION_CONFLICT_WEIGHT
    assert indication.bearing is Bearing.REFUTES


async def test_a_matching_passage_raises_nothing() -> None:
    assert await against(reported("https://reuters.com/a", MATCHING)) == ()


async def test_a_year_is_not_compared_against_a_rate() -> None:
    """Percentages compare with percentages, counts with counts.

    Without the comparability guard, a claim about a rate would read as disputed by any
    passage that happens to mention a year — the noisiest false positive available to a
    detector that only sees numbers.
    """
    dated = (
        "The figure has been published monthly since 2019 and is revised twice a "
        "year, according to the statistics authority's own methodology note."
    )
    found = await against(
        reported("https://ons.gov.uk/a", dated, matched=()), text=RATE_ONLY
    )
    assert found == ()


async def test_a_different_date_for_the_same_event_is_a_conflict() -> None:
    """The other side of the guard: two counts of the same kind do compare.

    The claim puts the decision in February 2026 and the passage puts it in 2019. That
    is a real disagreement about the same figure, and an agent that only ever compared
    percentages would miss every claim whose specifics are a date.
    """
    earlier = (
        "The equivalent decision came in 2019, after a run of three consecutive "
        "increases, according to the bank's own archive of policy statements."
    )
    (indication,) = await against(
        reported("https://reuters.com/a", earlier, matched=())
    )
    assert indication.weight == FIGURE_CONFLICT_WEIGHT
    assert "2019" in indication.detail


async def test_reviewers_who_split_are_the_conflict() -> None:
    found = await against(checks=rated("True", "False"))
    (indication,) = found
    assert indication.weight == REVIEWER_SPLIT_WEIGHT
    assert "did not agree" in indication.detail


async def test_reviewers_who_agreed_are_left_for_the_judge() -> None:
    """Unanimity is directional weight, and it belongs to exactly one agent.

    The pair of this test and the one above it is what stops one disagreement from being
    counted twice — once as a conflict here and once as a rating there.
    """
    assert await against(checks=rated("False", "Fake")) == ()


async def test_nothing_researched_produces_nothing() -> None:
    written = await ContradictionAgent()(GraphState(research=()))
    assert "conflicts" not in written
    assert written["trace"][0].agent == "contradiction"
