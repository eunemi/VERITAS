"""Shared artifact-level roll-up for the graph's deterministic judges.

The semantic judge and the deterministic judge produce the same claim shape. Their
shared aggregation lives here so one agent does not import another agent merely to
reuse the rules for an overall finding.
"""

from __future__ import annotations

from app.graph import scoring
from app.graph.state import GraphState
from app.graph.verdict import Assessment, ClaimRuling, Judgement, Ruling, Score

SETTLED_UNCERTAINTY = scoring.SETTLED_SHORTFALL / 100
UNGROUNDED_UNCERTAINTY = scoring.UNGROUNDED_SHORTFALL / 100

_HEADLINES: dict[Judgement, str] = {
    Judgement.SUPPORTED: "The claims examined are supported by the sources found",
    Judgement.REFUTED: "The sources found contradict at least one claim examined",
    Judgement.MIXED: "The sources found are divided on at least one claim examined",
    Judgement.UNCERTAIN: "The evidence found does not settle the claims examined",
}


def overall(rulings: tuple[ClaimRuling, ...]) -> Ruling:
    """Roll up claim findings, carrying the gravest finding rather than averaging it."""
    order = (
        Judgement.REFUTED,
        Judgement.MIXED,
        Judgement.UNCERTAIN,
        Judgement.SUPPORTED,
    )
    counts = {
        judgement: sum(1 for r in rulings if r.judgement is judgement)
        for judgement in order
    }
    judgement = next(judgement for judgement in order if counts[judgement])
    decided = [r for r in rulings if r.judgement is judgement]
    confidence = round(sum(r.confidence for r in decided) / len(decided), 4)
    parts = [
        f"{counts[judgement]} {judgement.value.lower()}"
        for judgement in order
        if counts[judgement]
    ]
    headline = _HEADLINES[judgement]
    if judgement is Judgement.UNCERTAIN and counts[Judgement.SUPPORTED]:
        headline = "Some claims are supported; others remain unverified"
    return Ruling(
        judgement=judgement,
        confidence=confidence,
        headline=headline,
        rationale=f"{len(rulings)} claim(s) examined: {', '.join(parts)}.",
        claims=rulings,
        score=carried(decided),
    )


def carried(decided: list[ClaimRuling]) -> Score | None:
    """Carry the least favorable score from the claims that set the roll-up."""
    scores = [r.score for r in decided if r.score is not None]
    if not scores:
        return None
    severity: dict[Assessment, int] = {
        Assessment.FALSE: 0,
        Assessment.MOSTLY_FALSE: 1,
        Assessment.UNCERTAIN: 2,
        Assessment.MOSTLY_TRUE: 3,
        Assessment.TRUE: 4,
    }
    worst = min(scores, key=lambda score: severity[score.assessment])
    return Score(
        value=round(sum(score.value for score in scores) / len(scores)),
        assessment=worst.assessment,
        insufficiency=worst.insufficiency,
        contested=worst.contested,
    )


def nothing_to_check(state: GraphState) -> Ruling:
    """Build the honest finding for an artifact with no checkable claims."""
    skipped = state.get("skipped", ())
    reason = (
        f"{len(skipped)} clause(s) were set aside as not checkable"
        if skipped
        else "nothing checkable was found in the artifact"
    )
    rationale = f"{reason}, so no claim was searched for and none can be ruled on."
    return Ruling(
        judgement=Judgement.UNCERTAIN,
        confidence=UNGROUNDED_UNCERTAINTY,
        headline="No checkable claim was examined",
        rationale=rationale,
        score=scoring.declined(rationale, searched=False),
    )
