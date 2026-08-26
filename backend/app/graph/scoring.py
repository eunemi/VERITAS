"""The 0–100 confidence score, from five inputs, and the finding it supports.

Five things move the number, and each is a :class:`~app.graph.verdict.Component` on the
result rather than a term folded into a total:

``credibility``
    how well the sources bearing on the claim stand up *as sources*.
``confirmation``
    how many independent publishers reached the same material.
``evidence``
    how much weight backs the side the finding goes with.
``recency``
    whether the material still describes the world.
``contradictions``
    a deduction, for how much of the weight pointed the other way.

The first four are budgets that sum to 100. The fifth is spent against that total, so
the same evidence read twice cannot inflate a score once and again.

**The score is confidence, not probability.** A firmly refuted claim scores high — 100
means "we are as sure of this finding as material like this allows", and the finding
itself is :class:`~app.graph.verdict.Assessment`. The two together are what a reader
needs; either alone is misleading.

**UNCERTAIN is not the middle band.** A claim reaches it by failing a gate, never by
landing between MOSTLY_TRUE and MOSTLY_FALSE, and :func:`declined` is the shape for a
claim that never reached the scale at all.
"""

from __future__ import annotations

from datetime import datetime

from app.domain import Credibility, Source
from app.graph.verdict import (
    Assessment,
    Bearing,
    Component,
    Indication,
    Judgement,
    Score,
    Thresholds,
)

__all__ = ["Score", "as_judgement", "declined", "score"]

#: The four positive budgets. They sum to 100 and ``test_graph_scoring`` says so.
CREDIBILITY_POINTS = 25
CONFIRMATION_POINTS = 30
EVIDENCE_POINTS = 30
RECENCY_POINTS = 15

#: The most a contested claim can lose. Deducted from the total above, not netted off
#: the evidence that earned it — see :func:`_contradictions`.
CONTRADICTION_PENALTY = 25

#: The ceiling on any score. Nothing assembled from search snippets and other people's
#: published ratings earns a number that reads as settled fact, however lopsided.
MAX_SCORE = 90

#: A claim scoring below this is not placed on the scale at all, however one-sided the
#: little that was found happens to be.
OPEN_SCORE = 40

#: What TRUE and FALSE cost, over and above the lean. Between the two, a finding is
#: MOSTLY, which is the honest reading of most of what search returns.
DECISIVE_SCORE = 70
DECISIVE_LEAN = 0.85

#: Indication weight at which ``evidence`` pays half its budget — about three
#: corroborating passages, or two unanimous reviews.
EVIDENCE_HALF = 2.0

#: Standing assumed for a source nobody graded, matching the judge's own reading of an
#: ungraded source: credibility scoring can be switched off, and a deployment that
#: switches it off must not thereby score every claim into the floor.
NEUTRAL = 0.5

#: Age in days at which ``recency`` starts and stops decaying.
FRESH_DAYS = 30
STALE_DAYS = 730

#: The share ``recency`` pays for material of unknown or exhausted age.
#:
#: The floor is the *same* for both, and deliberately: a set with no dates on it must
#: not outscore a set known to be old, or the cheapest way to a better score would be
#: to lose the dates. Not knowing when something was published is also not evidence
#: that it is stale, so the floor is well above nought.
UNDATED = 0.35

#: Scores for a claim the sufficiency gate stopped. High when the gathering worked and
#: the material simply did not settle the claim — that is a finding. Low when the
#: gathering itself came back empty, where the honest position is that little is known
#: about how little is known.
SETTLED_SHORTFALL = 50
UNGROUNDED_SHORTFALL = 25


def score(
    *,
    indications: tuple[Indication, ...],
    sources: tuple[Source, ...],
    grading: tuple[Credibility, ...] = (),
    now: datetime | None = None,
    thresholds: Thresholds | None = None,
) -> Score:
    """Confidence in a finding on one claim, and the finding.

    ``sources`` are the ones that carry a passage bearing on the claim; independence is
    counted here rather than trusted from the caller. ``now`` may be ``None``, which
    makes every source undated for scoring purposes — the same treatment as sources that
    genuinely carry no date, since in both cases no age is known.
    """
    limits = thresholds or Thresholds()
    support = sum(i.weight for i in indications if i.bearing is Bearing.SUPPORTS)
    refute = sum(i.weight for i in indications if i.bearing is Bearing.REFUTES)
    total = support + refute

    components = (
        _credibility(grading),
        _confirmation(sources, floor=limits.min_sources),
        _evidence(support, refute),
        _recency(sources, now=now),
        _contradictions(support, refute),
    )
    value = max(0, min(MAX_SCORE, round(sum(c.points for c in components))))

    # Nothing pointing either way is not a contest, and the lean cannot tell them
    # apart: an empty weighing and an evenly divided one both lean at nought. Checked
    # first, so the reason a reader gets is the one that happened.
    if not total:
        return Score(
            value=value,
            assessment=Assessment.UNCERTAIN,
            components=components,
            insufficiency="nothing found points either way on this claim",
        )

    # Two gates, both of which must pass before the claim goes on the scale, and each
    # catching what the other cannot. The *lean* is direction: which side the weight
    # fell on, and by how much of the total, so an evenly divided claim is stopped
    # however much material divided it. The *score* is substance: how much that
    # direction rests on, so a one-sided handful of weak, undated pages is stopped
    # however lopsided it was.
    #
    # Order matters. A divided claim usually also scores low — the deduction that makes
    # it divided is the same one that lowers the score — and of the two readings,
    # "the material contradicts itself" is the specific one and "there is not much of
    # it" the generic. Testing substance first would report every contested claim as
    # thin, and hide the one finding more searching cannot fix.
    lean = (support - refute) / total
    if abs(lean) < 1.0 - 2.0 * limits.contest_margin:
        return Score(
            value=value,
            assessment=Assessment.UNCERTAIN,
            components=components,
            insufficiency=(
                f"the material found points both ways in comparable measure "
                f"({support:.2f} for, {refute:.2f} against)"
            ),
            contested=True,
        )
    if value < OPEN_SCORE:
        return Score(
            value=value,
            assessment=Assessment.UNCERTAIN,
            components=components,
            insufficiency=(
                f"what was found scores {value}/100, below the {OPEN_SCORE} needed to "
                f"place this claim on the scale"
            ),
        )

    decisive = abs(lean) >= DECISIVE_LEAN and value >= DECISIVE_SCORE
    if lean > 0:
        assessment = Assessment.TRUE if decisive else Assessment.MOSTLY_TRUE
    else:
        assessment = Assessment.FALSE if decisive else Assessment.MOSTLY_FALSE
    return Score(value=value, assessment=assessment, components=components)


def declined(reason: str, *, searched: bool) -> Score:
    """The score for a claim the sufficiency gate stopped before any weighing.

    A number is still published rather than withheld. The gate outcome is itself a
    statement about how little was established, and a caller drawing a bar has to draw
    something; what must not be read as a position on the truth scale is the
    assessment, and that is UNCERTAIN with ``reason`` attached.
    """
    return Score(
        value=SETTLED_SHORTFALL if searched else UNGROUNDED_SHORTFALL,
        assessment=Assessment.UNCERTAIN,
        insufficiency=reason,
    )


def as_judgement(result: Score) -> Judgement:
    """``result`` in the four-way vocabulary the desk boundary consumes.

    The five-point scale has no MIXED, so a disputed claim and an unevidenced one both
    arrive here as UNCERTAIN; :attr:`~app.graph.verdict.Score.contested` is what tells
    them apart, and it matters at this boundary because the frontend renders CONTESTED
    as adverse and INSUFFICIENT as merely open.
    """
    if result.assessment is Assessment.UNCERTAIN:
        return Judgement.MIXED if result.contested else Judgement.UNCERTAIN
    if result.assessment in (Assessment.TRUE, Assessment.MOSTLY_TRUE):
        return Judgement.SUPPORTED
    return Judgement.REFUTED


# ---------------------------------------------------------------- components ----


def _credibility(grading: tuple[Credibility, ...]) -> Component:
    """Mean standing of the graded sources.

    Mean rather than best: one authoritative page among five anonymous ones is a
    thinner basis than five authoritative ones, and taking the maximum would report
    them as the same.
    """
    standings = [c.standing for c in grading if c.standing is not None]
    quality = sum(standings) / len(standings) if standings else NEUTRAL
    detail = (
        f"{len(standings)} of {len(grading)} source(s) graded, mean standing "
        f"{quality:.2f}"
        if grading
        else "no source was graded, so standing is assumed neutral"
    )
    return Component(
        name="credibility",
        points=round(CREDIBILITY_POINTS * quality, 2),
        of=CREDIBILITY_POINTS,
        detail=detail,
    )


def _confirmation(sources: tuple[Source, ...], *, floor: int) -> Component:
    """Independent confirmation, saturating: the second source is worth several later ones.

    ``count / (count + floor)`` rather than a fraction of some target, because there is
    no number of sources at which a claim is finished. It pays half the budget at the
    gate's own minimum and approaches the rest without ever arriving, which is the
    shape of the underlying fact — corroboration accumulates and never completes.
    """
    count = _independent(sources)
    share = count / (count + floor) if count else 0.0
    return Component(
        name="confirmation",
        points=round(CONFIRMATION_POINTS * share, 2),
        of=CONFIRMATION_POINTS,
        detail=(
            f"{count} independent publisher(s) among {len(sources)} source(s) bearing "
            f"on the claim"
        ),
    )


def _evidence(support: float, refute: float) -> Component:
    """How much weight backs the side the finding will go with.

    The winning side alone. Subtracting the loser here would charge a disagreement
    twice — :func:`_contradictions` is where it is charged — and would score a claim
    with strong evidence on both sides below one with no evidence at all.
    """
    backing = max(support, refute)
    share = backing / (backing + EVIDENCE_HALF)
    return Component(
        name="evidence",
        points=round(EVIDENCE_POINTS * share, 2),
        of=EVIDENCE_POINTS,
        detail=f"{support:.2f} supporting, {refute:.2f} contradicting",
    )


def _recency(sources: tuple[Source, ...], *, now: datetime | None) -> Component:
    """Freshness of the best-dated source, which is a term in confidence, not credit.

    :mod:`app.research.credibility` never charges a source for being old, and is right
    not to: a 1974 statute is not a worse source than yesterday's blog. This asks the
    other question — whether what was gathered still describes the world — and the
    freshest date is the one that answers it, since a single current confirmation makes
    the older material corroborating rather than stale.
    """
    dated = [s.published_at for s in sources if s.published_at is not None]
    if not dated or now is None:
        return Component(
            name="recency",
            points=round(RECENCY_POINTS * UNDATED, 2),
            of=RECENCY_POINTS,
            detail=(
                f"no publication date is known for any of {len(sources)} source(s)"
                if now is not None
                else "the retrieval time was not recorded, so no age could be read"
            ),
        )

    freshest = max(dated)
    age = max(0, (now - freshest).days)
    if age <= FRESH_DAYS:
        decay = 1.0
    elif age >= STALE_DAYS:
        decay = 0.0
    else:
        decay = 1.0 - (age - FRESH_DAYS) / (STALE_DAYS - FRESH_DAYS)
    share = UNDATED + (1.0 - UNDATED) * decay
    return Component(
        name="recency",
        points=round(RECENCY_POINTS * share, 2),
        of=RECENCY_POINTS,
        detail=f"the most recent source bearing on the claim is {age} day(s) old",
    )


def _contradictions(support: float, refute: float) -> Component:
    """The deduction for live disagreement, taken on the losing side's share.

    This reads the same two numbers as :func:`_evidence` and is not double-counting
    them: the finding's direction and strength come from the larger side, and this comes
    from the smaller. A claim carried three-to-one and one carried three-to-nothing
    lean the same way, and only one of them has something arguing back.
    """
    total = support + refute
    contest = min(support, refute) / total if total else 0.0
    return Component(
        name="contradictions",
        points=-round(CONTRADICTION_PENALTY * contest, 2),
        of=-CONTRADICTION_PENALTY,
        detail=(
            f"{contest:.0%} of the weight found points against the finding"
            if contest
            else "nothing found points against the finding"
        ),
    )


def _independent(sources: tuple[Source, ...]) -> int:
    """Distinct publishers, with syndicated copies of one story counted once.

    The only count that means anything here. Eight mastheads carrying one wire report
    is one confirmation, and counting it as eight would let the wire manufacture the
    corroboration this component exists to measure.
    """
    domains: set[str] = set()
    clusters: set[int] = set()
    count = 0
    for source in sources:
        if source.domain in domains:
            continue
        if source.cluster is not None and source.cluster in clusters:
            continue
        domains.add(source.domain)
        if source.cluster is not None:
            clusters.add(source.cluster)
        count += 1
    return count
