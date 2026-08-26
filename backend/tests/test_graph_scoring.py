"""The 0–100 score: what moves it, what caps it, and where UNCERTAIN comes from.

Every number asserted below was read off the real module and then reasoned about, not
predicted from the constants. Where a figure is exact it is exact because the arithmetic
is published on :class:`~app.graph.verdict.Component` and a reader can recompute it; the
tests that would still pass if a weight were retuned are written as inequalities on
purpose, so retuning does not have to fight this file.

Three properties matter more than any individual figure, and each has a section:

**The score is confidence, not probability.** A firmly refuted claim and a firmly
supported one score the same. Anything else would make a high number mean "true", and
then every UNCERTAIN would read as a hedged truth claim.

**UNCERTAIN is a gate, never a band.** There is no lean at which a claim slides from
MOSTLY_TRUE to UNCERTAIN to MOSTLY_FALSE. It is reached by failing one of three
checks — nothing pointing either way, a divided balance, too little substance — and
which one is on :attr:`~app.graph.verdict.Score.insufficiency`.

**Syndication buys nothing.** Eight mastheads carrying one wire report must not score
above one masthead, because the whole confirmation budget is otherwise purchasable.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain import Source
from app.graph import scoring
from app.graph.verdict import (
    Assessment,
    Bearing,
    Component,
    Indication,
    Judgement,
    Score,
    Thresholds,
)
from tests.graph_bench import NOW, graded, reported

#: A date inside :data:`app.graph.scoring.FRESH_DAYS` of the sources ``reported`` makes,
#: for the runs that want recency saturated rather than exercised.
JUST_AFTER = datetime(2026, 2, 10, tzinfo=UTC)

#: Long enough after them to exhaust :data:`app.graph.scoring.STALE_DAYS`.
MUCH_LATER = datetime(2029, 1, 1, tzinfo=UTC)


def supports(weight: float = 1.0) -> Indication:
    return Indication(agent="t", bearing=Bearing.SUPPORTS, weight=weight, detail="d")


def refutes(weight: float = 1.0) -> Indication:
    return Indication(agent="t", bearing=Bearing.REFUTES, weight=weight, detail="d")


def publishers(count: int, *, cluster: int | None = None) -> tuple[Source, ...]:
    """``count`` distinct domains, optionally all telling the same story."""
    return tuple(
        reported(f"https://r{index}.example/a", ref=index, cluster=cluster)
        for index in range(1, count + 1)
    )


def rate(
    indications: tuple[Indication, ...],
    sources: tuple[Source, ...],
    *,
    now: datetime | None = NOW,
    grade: bool = True,
) -> Score:
    return scoring.score(
        indications=indications,
        sources=sources,
        grading=graded(sources) if grade else (),
        now=now,
    )


def part(result: Score, name: str) -> Component:
    """One named component of a score, so a test can assert on it alone."""
    return next(c for c in result.components if c.name == name)


# ------------------------------------------------------------- the 0-100 ----


def test_the_four_budgets_are_a_hundred_and_the_deduction_is_separate() -> None:
    """The invariant that makes a component's ``points / of`` readable as a share.

    The deduction is deliberately outside the total. Folding it in would mean a claim
    with strong evidence on both sides scored below one with no evidence at all, since
    it would be paying for the disagreement twice — once in a smaller winning side and
    once again in the penalty.
    """
    assert (
        scoring.CREDIBILITY_POINTS
        + scoring.CONFIRMATION_POINTS
        + scoring.EVIDENCE_POINTS
        + scoring.RECENCY_POINTS
    ) == 100
    assert scoring.CONTRADICTION_PENALTY > 0


def test_the_components_recompute_to_the_score() -> None:
    """The published arithmetic is the arithmetic, not a parallel explanation of it."""
    result = rate((supports(), supports(), refutes(0.3)), publishers(3))
    assert result.value == round(sum(c.points for c in result.components))
    assert {c.name for c in result.components} == {
        "credibility",
        "confirmation",
        "evidence",
        "recency",
        "contradictions",
    }


def test_no_score_reads_as_settled_fact() -> None:
    """Twenty publishers and forty corroborations, and it still stops at the ceiling.

    The raw total here clears 91, so the cap is doing work rather than sitting above a
    number nothing reaches. Everything the graph weighs is a search snippet or somebody
    else's published rating, and no quantity of either is grounds for a number that
    prints as certainty.
    """
    fleet = publishers(20)
    result = scoring.score(
        indications=tuple(supports() for _ in range(40)),
        sources=fleet,
        grading=graded(fleet),
        now=JUST_AFTER,
    )
    assert sum(c.points for c in result.components) > scoring.MAX_SCORE
    assert result.value == scoring.MAX_SCORE
    assert result.assessment is Assessment.TRUE


@pytest.mark.parametrize("value", [-1, 101])
def test_a_score_outside_the_scale_is_refused(value: int) -> None:
    """Guards the guard: the 0–100 range is the one thing a caller cannot get wrong.

    :attr:`app.domain.verification.Verdict.confidence` runs 0–1 and rejects ``92`` for
    ninety-two percent. The two scales meet on a :class:`~app.graph.verdict.ClaimRuling`,
    and a bound at each end is what keeps a mix-up loud.
    """
    with pytest.raises(ValueError, match="between 0 and 100"):
        Score(value=value, assessment=Assessment.TRUE)


def test_a_reason_is_required_for_uncertain_and_forbidden_otherwise() -> None:
    """An UNCERTAIN with no reason is the failure this whole design is against.

    It would be indistinguishable, to a reader, from a hedge — and the point of keeping
    UNCERTAIN off the truth scale is that it says something specific instead.
    """
    with pytest.raises(ValueError, match="requires a reason"):
        Score(value=50, assessment=Assessment.UNCERTAIN)
    with pytest.raises(ValueError, match="forbids one"):
        Score(value=80, assessment=Assessment.TRUE, insufficiency="why")


# ------------------------------------------------- confidence, not truth ----


def test_a_refuted_claim_scores_exactly_as_high_as_a_supported_one() -> None:
    """The score measures how sure the finding is, not how true the claim is.

    Reversing every bearing must leave the number alone and flip only the assessment. A
    scale on which FALSE scored low would be a probability of truth wearing a
    confidence's name, and every UNCERTAIN on it would read as a hedged TRUE.
    """
    trio = publishers(3)
    upheld = rate((supports(), supports(), supports(), supports()), trio)
    denied = rate((refutes(), refutes(), refutes(), refutes()), trio)
    assert upheld.value == denied.value == 73
    assert upheld.assessment is Assessment.TRUE
    assert denied.assessment is Assessment.FALSE


@pytest.mark.parametrize(
    ("assessment", "judgement"),
    [
        (Assessment.TRUE, Judgement.SUPPORTED),
        (Assessment.MOSTLY_TRUE, Judgement.SUPPORTED),
        (Assessment.MOSTLY_FALSE, Judgement.REFUTED),
        (Assessment.FALSE, Judgement.REFUTED),
    ],
)
def test_every_placed_assessment_reaches_the_desk_boundary(
    assessment: Assessment, judgement: Judgement
) -> None:
    """Total over the four placed members, so a new one cannot be added silently."""
    assert scoring.as_judgement(Score(value=80, assessment=assessment)) is judgement


def test_the_vocabulary_is_exactly_the_five_asked_for() -> None:
    assert [a.value for a in Assessment] == [
        "TRUE",
        "MOSTLY_TRUE",
        "UNCERTAIN",
        "MOSTLY_FALSE",
        "FALSE",
    ]


# --------------------------------------------------- UNCERTAIN as a gate ----


def test_nothing_pointing_either_way_is_not_a_disagreement() -> None:
    """An empty weighing and an evenly divided one both lean at nought.

    They are opposite findings — one is silence, the other is a dispute — and only the
    second may reach :attr:`Judgement.MIXED`. Reading the lean alone cannot tell them
    apart, which is why the total is checked before it.
    """
    result = rate((), publishers(3))
    assert result.assessment is Assessment.UNCERTAIN
    assert not result.contested
    assert result.insufficiency == "nothing found points either way on this claim"
    assert scoring.as_judgement(result) is Judgement.UNCERTAIN


def test_an_evenly_divided_claim_is_uncertain_and_says_so() -> None:
    """Not MOSTLY anything. Both sides substantial, so neither is reported alone."""
    result = rate((supports(), refutes()), publishers(3))
    assert result.assessment is Assessment.UNCERTAIN
    assert result.contested
    assert "points both ways" in result.insufficiency
    assert scoring.as_judgement(result) is Judgement.MIXED


def test_a_thinly_evidenced_claim_is_uncertain_however_one_sided() -> None:
    """One weak indication from one ungraded, undated page. Lean of 1.0, and still open.

    This is the gate the lean cannot supply: the evidence points one way unanimously,
    and there is not enough of it to say so.
    """
    result = rate((supports(0.2),), (reported("https://a.example/a", dated=False),), grade=False)
    assert result.value == 30
    assert result.assessment is Assessment.UNCERTAIN
    assert not result.contested
    assert f"below the {scoring.OPEN_SCORE}" in result.insufficiency
    assert scoring.as_judgement(result) is Judgement.UNCERTAIN


def test_a_claim_that_is_both_divided_and_thin_is_reported_as_divided() -> None:
    """The ordering of the two gates, and it is not arbitrary.

    A divided claim usually also scores low — the deduction that divides it is the same
    one that lowers the score — so testing substance first would report every contested
    claim as merely thin. The difference matters to a reader: thin is fixed by searching
    harder, and divided is not fixed by anything.
    """
    weak = (reported("https://a.example/a", dated=False),)
    result = rate((supports(0.2), refutes(0.2)), weak, grade=False)
    assert result.value < scoring.OPEN_SCORE
    assert result.contested
    assert "points both ways" in result.insufficiency


def test_a_declined_claim_publishes_a_number_and_a_reason() -> None:
    """The sufficiency gate's shape. Lower when the gathering itself came back empty.

    A number is published rather than withheld because a caller drawing a bar has to
    draw something; what must not be read as a position on the scale is the assessment.
    """
    settled = scoring.declined("nothing settled it", searched=True)
    ungrounded = scoring.declined("nothing was gathered", searched=False)
    assert settled.value == scoring.SETTLED_SHORTFALL > ungrounded.value
    assert ungrounded.value == scoring.UNGROUNDED_SHORTFALL
    for result in (settled, ungrounded):
        assert result.assessment is Assessment.UNCERTAIN
        assert not result.contested
        assert not result.components
        assert scoring.as_judgement(result) is Judgement.UNCERTAIN


# ------------------------------------------------------- the five inputs ----


def test_better_sources_score_higher_and_ungraded_ones_score_neutral() -> None:
    """Credibility moves the score, and switching grading off does not floor it.

    ``CREDIBILITY_ENABLED=False`` is a real deployment. A component that paid nothing
    for an ungraded source would let one configuration flag decide every claim, which is
    the same reasoning behind the judge's own treatment of an ungraded source.
    """
    trio = publishers(3)
    assert part(rate((supports(),), trio, grade=False), "credibility").points == pytest.approx(
        scoring.CREDIBILITY_POINTS * scoring.NEUTRAL
    )
    assert part(rate((supports(),), trio), "credibility").points > 0


def test_independent_confirmation_saturates_rather_than_accumulating() -> None:
    """The second publisher is worth far more than the fifth, and none is worth all of it.

    There is no number of sources at which a claim is finished, so the curve approaches
    the budget without arriving. A component that paid out in full at some target would
    make everything past that target free.
    """
    points = [part(rate((supports(),), publishers(n)), "confirmation").points for n in (1, 2, 4, 8)]
    assert points == sorted(points)
    assert points[1] - points[0] > points[3] - points[2]
    assert points[-1] < scoring.CONFIRMATION_POINTS


def test_eight_copies_of_one_wire_report_do_not_outscore_one_source() -> None:
    """The property the confirmation budget exists to protect.

    Syndicated copies share a cluster and count once, so the eight score no better than
    the one — and in fact score below it, because
    :mod:`app.research.credibility` reads the same syndication as a mark against each
    copy's independence. Both directions are the point: the budget cannot be bought.
    """
    alone = rate((supports(), supports()), publishers(1))
    syndicated = rate((supports(), supports()), publishers(8, cluster=7))
    assert part(syndicated, "confirmation").points == part(alone, "confirmation").points
    assert syndicated.value <= alone.value


def test_the_evidence_budget_reads_the_winning_side_only() -> None:
    """More weight behind the finding scores higher; the losing side is not netted off here.

    Adding a contradiction lowers the total — through ``contradictions``, which is where
    that belongs — while leaving ``evidence`` exactly where it was. Netting the two here
    would charge one disagreement twice.
    """
    trio = publishers(3)
    thin = rate((supports(0.5),), trio)
    thick = rate((supports(), supports(), supports()), trio)
    assert part(thick, "evidence").points > part(thin, "evidence").points

    disputed = rate((supports(), supports(), supports(), refutes(0.4)), trio)
    assert part(disputed, "evidence").points == part(thick, "evidence").points
    assert disputed.value < thick.value


def test_fresh_material_outscores_old_material() -> None:
    trio = publishers(3)
    fresh = part(rate((supports(),), trio, now=JUST_AFTER), "recency")
    aged = part(rate((supports(),), trio, now=MUCH_LATER), "recency")
    assert fresh.points == scoring.RECENCY_POINTS
    assert aged.points < fresh.points


def test_losing_a_date_never_pays_better_than_having_an_old_one() -> None:
    """The floor is shared, and that is what removes the incentive to drop dates.

    If undated scored above exhausted-age, the cheapest route to a better score would be
    to stop recording publication dates. It is the *recency component* that is compared
    here, not the totals: an undated page also loses credibility axes, so its overall
    score is lower — which is the honest direction for that to run.
    """
    trio = publishers(3)
    undated = tuple(
        reported(f"https://r{i}.example/a", ref=i, dated=False) for i in (1, 2, 3)
    )
    assert part(rate((supports(),), undated), "recency").points == part(
        rate((supports(),), trio, now=MUCH_LATER), "recency"
    ).points
    assert part(rate((supports(),), undated), "recency").points > 0


def test_an_unrecorded_retrieval_time_is_treated_as_an_unknown_age() -> None:
    """``now=None`` is a caller that did not stamp the run, not a claim about the world.

    It reads as unknown age rather than as fresh, and the detail says which, so nobody
    reads a missing timestamp as a recent one.
    """
    result = rate((supports(),), publishers(3), now=None)
    recency = part(result, "recency")
    assert recency.points == part(rate((supports(),), publishers(3), now=MUCH_LATER), "recency").points
    assert "retrieval time" in recency.detail


def test_contradictions_are_charged_on_the_losing_share_not_its_size() -> None:
    """A share, so the deduction is about how contested a claim is, not how busy it is.

    One contradiction against one corroboration is a coin toss; one against nine is a
    footnote. Charging the absolute weight would make the second cost as much as the
    first, and would punish a well-researched claim for having found the objection.
    """
    trio = publishers(3)
    lone = part(rate((supports(), refutes()), trio), "contradictions")
    outnumbered = part(
        rate((*(supports() for _ in range(9)), refutes()), trio), "contradictions"
    )
    assert lone.points < outnumbered.points < 0
    assert part(rate((supports(),), trio), "contradictions").points == 0


# ------------------------------------------------------- where the lean lands ----


def test_a_lopsided_claim_is_decisive_and_a_narrow_one_is_only_mostly() -> None:
    """The ``MOSTLY`` steps, which are what a five-point scale is for.

    Both of these are SUPPORTED to the desk boundary and a reader is owed the
    difference: unanimous corroboration and a four-to-one split are not the same finding.
    """
    trio = publishers(3)
    unanimous = rate((supports(), supports(), supports(), supports()), trio)
    narrow = rate((supports(), supports(), supports(), supports(), refutes()), trio)
    assert unanimous.assessment is Assessment.TRUE
    assert narrow.assessment is Assessment.MOSTLY_TRUE
    assert narrow.value < unanimous.value


def test_a_lopsided_but_unsubstantial_claim_is_only_mostly() -> None:
    """TRUE costs a score as well as a lean, and this is the case that isolates the score.

    One corroboration from two publishers leans at 1.0 — nothing disputes it — and still
    reads as MOSTLY_TRUE, because ``DECISIVE_SCORE`` is not met. Without that second
    requirement, the strongest label on the scale would be available to any claim
    nobody had contradicted yet.
    """
    result = rate((supports(0.6),), publishers(2))
    assert scoring.OPEN_SCORE <= result.value < scoring.DECISIVE_SCORE
    assert result.assessment is Assessment.MOSTLY_TRUE


def test_the_contest_threshold_comes_from_the_judge_s_own_configuration() -> None:
    """One knob, so the gate a deployment tuned is the gate that runs.

    ``contest_margin`` is a share of the total, and the lean is a difference over it, so
    a margin of ``m`` is a lean of ``1 - 2m``: at the default 0.30 a claim needs 0.40 of
    the weight net to be placed at all.
    """
    trio = publishers(3)
    close = (supports(), supports(), refutes())
    assert scoring.score(
        indications=close, sources=trio, grading=graded(trio), now=NOW
    ).assessment is Assessment.UNCERTAIN
    assert scoring.score(
        indications=close,
        sources=trio,
        grading=graded(trio),
        now=NOW,
        thresholds=Thresholds(contest_margin=0.45),
    ).assessment is Assessment.MOSTLY_TRUE
