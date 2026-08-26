"""Weighs what the other agents found, and says when it cannot decide."""

from __future__ import annotations

from datetime import datetime

from app.domain import Band, Credibility, FactCheck, ProviderStatus, Source
from app.graph import scoring
from app.graph.state import AgentNote, Case, GraphState, cases
from app.graph.verdict import (
    PASSAGE_WEIGHT,
    STANCE_WEIGHTS,
    Assessment,
    Bearing,
    ClaimRuling,
    Indication,
    Judgement,
    Ruling,
    Score,
    Thresholds,
)

NAME = "judge"

#: How firmly the judge holds an UNCERTAIN, on the 0–1 scale the domain uses. The same
#: two numbers :mod:`app.graph.scoring` publishes, divided down rather than restated, so
#: the score on a ruling and its confidence cannot come to disagree.
SETTLED_UNCERTAINTY = scoring.SETTLED_SHORTFALL / 100
UNGROUNDED_UNCERTAINTY = scoring.UNGROUNDED_SHORTFALL / 100

#: The ceiling on any confidence. Nothing assembled from search snippets and other
#: people's ratings earns a number that reads as settled fact.
MAX_CONFIDENCE = scoring.MAX_SCORE / 100


class JudgeAgent:
    """Rules on each claim, then on the artifact.

    Two stages per claim, in this order and never merged. The **sufficiency gate**
    asks whether there is enough here to rule on at all; only what passes it reaches
    the **weighing**, which is :mod:`app.graph.scoring`. Merging them would let a claim
    with one weak source arrive at a confident verdict by having nothing to disagree
    with it, which is the failure this split exists to prevent.
    """

    def __init__(self, *, thresholds: Thresholds | None = None) -> None:
        self._limits = thresholds or Thresholds()

    async def __call__(self, state: GraphState) -> GraphState:
        found = cases(state)
        if not found:
            return GraphState(
                ruling=_nothing_to_check(state),
                trace=(AgentNote(NAME, "no claims reached the judge"),),
            )

        searched = _searched(state)
        now = state.get("now")
        rulings = tuple(
            self._rule(case, searched=searched, now=now) for case in found
        )
        ruling = _overall(rulings)
        return GraphState(
            ruling=ruling,
            trace=(
                AgentNote(NAME, f"{ruling.judgement.value} across {len(rulings)} claim(s)"),
            ),
        )

    # -------------------------------------------------------------- one claim ---

    def _rule(
        self, case: Case, *, searched: bool, now: datetime | None
    ) -> ClaimRuling:
        shortfall = self._insufficient(case, searched=searched)
        if shortfall:
            return _ruling(case, scoring.declined(shortfall, searched=searched))

        indications = (
            *self._from_reviews(case.fact_checks),
            *self._from_passages(case),
            *case.conflicts,
        )
        support = sum(i.weight for i in indications if i.bearing is Bearing.SUPPORTS)
        refute = sum(i.weight for i in indications if i.bearing is Bearing.REFUTES)

        # Sources that stand up and bear on the claim, but nothing among them points
        # either way — a real outcome, and the one a scale from true to false has no
        # room for. Checked before scoring rather than left to the score's own floor:
        # this is a statement that nothing was established, not a low confidence in
        # something that was.
        if support + refute < self._limits.min_weight:
            return _ruling(
                case,
                scoring.declined(
                    "sources bear on this claim but none of them settles it either way",
                    searched=True,
                ),
                support=support,
                refute=refute,
                indications=indications,
            )

        return _ruling(
            case,
            scoring.score(
                indications=indications,
                sources=self._standing_sources(case),
                grading=case.grading,
                now=now,
                thresholds=self._limits,
            ),
            support=support,
            refute=refute,
            indications=indications,
        )

    # ------------------------------------------------------ sufficiency gate ---

    def _insufficient(self, case: Case, *, searched: bool) -> str:
        """Why this claim cannot be ruled on. Empty when it can."""
        if not searched:
            return "no search provider answered, so nothing was gathered to weigh"
        if not case.sources:
            return "the search returned no sources for this claim"

        standing = self._standing_sources(case)
        if not standing:
            return (
                f"no source carrying a passage on this claim reached a standing of "
                f"{self._limits.min_standing}"
            )
        if len(standing) < self._limits.min_sources:
            return (
                f"{len(standing)} independent source(s) bear on this claim, below the "
                f"{self._limits.min_sources} required to rule on it"
            )
        return ""

    def _standing_sources(self, case: Case) -> tuple[Source, ...]:
        """Sources that carry a passage, reach the standing floor, and are distinct.

        Distinctness is the point of the count. Three copies of one wire story is one
        source that was easy to find; counting them as three would let syndication
        manufacture the corroboration this gate exists to require.
        """
        kept: list[Source] = []
        seen_clusters: set[int] = set()
        seen_domains: set[str] = set()
        for source in case.sources:
            if not source.evidence:
                continue
            grade = case.credibility_of(source.ref)
            if not _stands(grade, self._limits.min_standing):
                continue
            if source.domain in seen_domains:
                continue
            if source.cluster is not None and source.cluster in seen_clusters:
                continue
            seen_domains.add(source.domain)
            if source.cluster is not None:
                seen_clusters.add(source.cluster)
            kept.append(source)
        return tuple(kept)

    # ------------------------------------------------------------- weighing ---

    def _from_reviews(self, checks: tuple[FactCheck, ...]) -> tuple[Indication, ...]:
        """Directional weight from reviewers who all read the claim the same way.

        Only the unanimous case. A split is the contradiction agent's finding, and
        weighing it here as well would count one disagreement twice.
        """
        found: list[Indication] = []
        for check in checks:
            stance = check.agreement
            if stance is None or stance not in STANCE_WEIGHTS:
                continue
            bearing, weight = STANCE_WEIGHTS[stance]
            found.append(
                Indication(
                    agent=NAME,
                    bearing=bearing,
                    weight=weight,
                    detail=(
                        f"{', '.join(check.publishers)} rated this claim "
                        f"{stance.value} (match {check.match:.2f})"
                    ),
                )
            )
        return tuple(found)

    def _from_passages(self, case: Case) -> tuple[Indication, ...]:
        """Corroboration from passages that repeat the claim's own specifics.

        Scaled by the source's standing rather than counted flat, so a page whose
        publisher and date could not be established contributes less than one whose
        could. Only figure and entity matches corroborate: shared topic words mean the
        passage is about the same thing, which is not the same as confirming it.
        """
        found: list[Indication] = []
        for source in self._standing_sources(case):
            grade = case.credibility_of(source.ref)
            standing = grade.standing if grade and grade.standing else 0.5
            for passage in source.evidence:
                if not (passage.matched_numbers or passage.matched_entities):
                    continue
                matched = ", ".join(
                    passage.matched_numbers or passage.matched_entities
                )
                found.append(
                    Indication(
                        agent=NAME,
                        bearing=Bearing.SUPPORTS,
                        weight=round(PASSAGE_WEIGHT * standing, 4),
                        detail=f"{source.domain} repeats the claim's {matched}",
                        ref=source.ref,
                    )
                )
                break
        return tuple(found)


# ------------------------------------------------------------------- overall ---


def _ruling(
    case: Case,
    result: Score,
    *,
    support: float = 0.0,
    refute: float = 0.0,
    indications: tuple[Indication, ...] = (),
) -> ClaimRuling:
    """One claim's finding, assembled around a score rather than beside one."""
    return ClaimRuling(
        ref=case.claim.ref,
        claim=case.claim.text,
        judgement=scoring.as_judgement(result),
        confidence=result.value / 100,
        support=round(support, 4),
        refute=round(refute, 4),
        indications=indications,
        insufficiency=result.insufficiency,
        score=result,
    )


def _overall(rulings: tuple[ClaimRuling, ...]) -> Ruling:
    """One finding for the artifact, from the findings on its claims.

    The worst outcome carries. An artifact holding one refuted claim among four
    supported ones is not mostly true, and averaging the four would report it that
    way; a reader needs the refutation to survive the summary.
    """
    order = (
        Judgement.REFUTED,
        Judgement.MIXED,
        Judgement.UNCERTAIN,
        Judgement.SUPPORTED,
    )
    counts = {j: sum(1 for r in rulings if r.judgement is j) for j in order}
    judgement = next(j for j in order if counts[j])
    decided = [r for r in rulings if r.judgement is judgement]
    confidence = round(sum(r.confidence for r in decided) / len(decided), 4)

    parts = [f"{counts[j]} {j.value.lower()}" for j in order if counts[j]]
    return Ruling(
        judgement=judgement,
        confidence=confidence,
        headline=_HEADLINES[judgement],
        rationale=f"{len(rulings)} claim(s) examined: {', '.join(parts)}.",
        claims=rulings,
        score=_carried(decided),
    )


def _carried(decided: list[ClaimRuling]) -> Score | None:
    """The artifact's score, from the claims that set its judgement and no others.

    Averaged over that group rather than over everything examined, for the same reason
    the judgement takes the worst rather than the mean: the confidence on the summary
    has to be the confidence in *the finding being summarised*. Folding three
    comfortably supported claims into a refutation's number would report the artifact as
    barely refuted when nothing about the refutation was marginal.

    The assessment is the most adverse in the group, which within a single judgement is
    also the least decisive one on the supported side — MOSTLY_TRUE beside TRUE reads as
    MOSTLY_TRUE, and FALSE beside MOSTLY_FALSE reads as FALSE.
    """
    scores = [r.score for r in decided if r.score is not None]
    if not scores:
        return None
    worst = min(scores, key=lambda s: _SEVERITY[s.assessment])
    return Score(
        value=round(sum(s.value for s in scores) / len(scores)),
        assessment=worst.assessment,
        insufficiency=worst.insufficiency,
        contested=worst.contested,
    )


def _searched(state: GraphState) -> bool:
    """Whether any provider actually answered.

    Read off the outcomes' status rather than their result counts. A provider that
    searched and found nothing is a statement about the world; one that was never
    configured, or failed, is a statement about this deployment, and the two must not
    reach the reader as the same sentence.
    """
    return any(
        o.status in (ProviderStatus.SEARCHED, ProviderStatus.PARTIAL)
        for o in state.get("providers", ())
    )


def _nothing_to_check(state: GraphState) -> Ruling:
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


def _stands(grade: Credibility | None, floor: float) -> bool:
    """Whether a source clears the standing floor.

    An ungraded source is not excluded — grading can be switched off, and a gate that
    silently required it would make one config flag decide every verdict.
    """
    if grade is None:
        return True
    if grade.band is Band.UNKNOWN:
        return False
    return grade.standing is not None and grade.standing >= floor


#: Most adverse first, for picking the assessment that carries a whole artifact.
_SEVERITY: dict[Assessment, int] = {
    Assessment.FALSE: 0,
    Assessment.MOSTLY_FALSE: 1,
    Assessment.UNCERTAIN: 2,
    Assessment.MOSTLY_TRUE: 3,
    Assessment.TRUE: 4,
}


_HEADLINES: dict[Judgement, str] = {
    Judgement.SUPPORTED: "The claims examined are supported by the sources found",
    Judgement.REFUTED: "The sources found contradict at least one claim examined",
    Judgement.MIXED: "The sources found are divided on at least one claim examined",
    Judgement.UNCERTAIN: "The evidence found does not settle the claims examined",
}
