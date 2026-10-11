"""Weighs what the other agents found, and says when it cannot decide."""

from __future__ import annotations

from datetime import datetime

from app.domain import Band, Credibility, FactCheck, ProviderStatus, Source
from app.graph import rollup, scoring
from app.graph.rollup import nothing_to_check as _nothing_to_check
from app.graph.rollup import overall as _overall
from app.graph.state import AgentNote, Case, GraphState, cases
from app.graph.verdict import (
    PASSAGE_WEIGHT,
    STANCE_WEIGHTS,
    Bearing,
    ClaimRuling,
    Indication,
    Score,
    Thresholds,
)

NAME = "judge"
SETTLED_UNCERTAINTY = rollup.SETTLED_UNCERTAINTY
UNGROUNDED_UNCERTAINTY = rollup.UNGROUNDED_UNCERTAINTY


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
        rulings = tuple(self._rule(case, searched=searched, now=now) for case in found)
        ruling = _overall(rulings)
        return GraphState(
            ruling=ruling,
            trace=(
                AgentNote(
                    NAME, f"{ruling.judgement.value} across {len(rulings)} claim(s)"
                ),
            ),
        )

    # -------------------------------------------------------------- one claim ---

    def _rule(self, case: Case, *, searched: bool, now: datetime | None) -> ClaimRuling:
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
                matched = ", ".join(passage.matched_numbers or passage.matched_entities)
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
