"""The decision desk: which filed determination the record publishes, and why.

It re-examines nothing, so there is nothing to fake here — every test below is the
adjudicator handed reports and asked what it signs. What that makes testable is the
one decision it owns: :data:`~app.desks.decision.GRAVITY`, the order the reports are
read in.

The three properties worth breaking a build over:

* an adverse finding from one desk is never averaged away by affirmative findings
  from others;
* ``INSUFFICIENT`` outranks every affirmative, because "one desk confirmed it and
  another could not check it" is not a confirmation;
* the confidence published is the mean over the *deciding* desks only, so a confident
  desk that did not reach the governing determination cannot move the number.
"""

from __future__ import annotations

import pytest

from app.desks import Adjudicator, adjudicators
from app.desks.decision import (
    GRAVITY,
    HEADLINES,
    NOTHING_FILED,
    DecisionDesk,
    build,
)
from app.domain import (
    ADJUDICATOR,
    Desk,
    DeskReport,
    Determination,
    LedgerEntry,
    Verdict,
)
from tests.stubs import canned, furnished


def filed(
    desk: Desk, determination: Determination, *, confidence: float = 0.5
) -> DeskReport:
    return DeskReport(
        desk=desk,
        verdict=Verdict(
            determination=determination,
            headline=f"{desk.value} reporting",
            rationale=f"What the {desk.value} desk found.",
            confidence=confidence,
        ),
        ledger=(LedgerEntry(key="Desk", value=desk.value),),
    )


# ------------------------------------------------------------------- the seam ----


def test_it_is_the_registered_adjudicator() -> None:
    assert adjudicators.factory(ADJUDICATOR) is not None
    assert isinstance(adjudicators.resolve(ADJUDICATOR), DecisionDesk)


def test_it_satisfies_the_protocol_and_claims_the_right_desk() -> None:
    desk = build()
    assert isinstance(desk, Adjudicator)
    assert desk.desk is ADJUDICATOR
    # The factory takes settings so binding it looks like binding any other desk,
    # and ignores them because it has nothing to configure.
    assert isinstance(build(None), DecisionDesk)


def test_it_is_not_an_examiner() -> None:
    """Adjudicating and examining are separate contracts; this desk has only one."""
    assert not hasattr(DecisionDesk, "examine")
    assert not hasattr(DecisionDesk, "kinds")


# ------------------------------------------------------------------- gravity ----


def test_gravity_covers_every_determination() -> None:
    """A determination missing from the order would raise ``StopIteration`` in
    ``_governing`` the first time a desk filed it."""
    assert set(GRAVITY) == set(Determination)
    assert len(GRAVITY) == len(Determination)


def test_every_determination_can_be_stated_to_a_reader() -> None:
    assert set(HEADLINES) == set(Determination)


@pytest.mark.parametrize("adverse", [d for d in GRAVITY[:4]])
async def test_one_adverse_finding_is_never_averaged_away(
    adverse: Determination,
) -> None:
    signed = await DecisionDesk().adjudicate(
        [
            filed(Desk.TEXT, Determination.CLEAR, confidence=0.99),
            filed(Desk.IMAGE, Determination.CLEAR, confidence=0.99),
            filed(Desk.FACT_CHECK, adverse, confidence=0.31),
        ]
    )
    assert signed.verdict.determination is adverse
    assert signed.verdict.confidence == pytest.approx(0.31)


async def test_insufficient_outranks_every_affirmative() -> None:
    for affirmative in (
        Determination.SUPPORTED,
        Determination.CONSISTENT,
        Determination.CLEAR,
    ):
        signed = await DecisionDesk().adjudicate(
            [
                filed(Desk.TEXT, affirmative, confidence=0.9),
                filed(Desk.AUDIO, Determination.INSUFFICIENT, confidence=0.0),
            ]
        )
        assert signed.verdict.determination is Determination.INSUFFICIENT


async def test_requires_verification_never_outranks_a_finding() -> None:
    """It is a desk asking for a check, not the result of one."""
    signed = await DecisionDesk().adjudicate(
        [
            filed(Desk.IMAGE, Determination.REQUIRES_VERIFICATION, confidence=0.95),
            filed(Desk.FACT_CHECK, Determination.CLEAR, confidence=0.2),
        ]
    )
    assert signed.verdict.determination is Determination.CLEAR


async def test_a_stronger_affirmative_wins_over_a_weaker_one() -> None:
    signed = await DecisionDesk().adjudicate(
        [
            filed(Desk.TEXT, Determination.CLEAR, confidence=0.8),
            filed(Desk.FACT_CHECK, Determination.SUPPORTED, confidence=0.6),
        ]
    )
    assert signed.verdict.determination is Determination.SUPPORTED


async def test_the_order_is_read_off_gravity_and_not_off_the_reports() -> None:
    """Filing order does not matter; the gravity order does."""
    reports = [filed(Desk.TEXT, d) for d in reversed(GRAVITY)]
    signed = await DecisionDesk().adjudicate(reports)
    assert signed.verdict.determination is GRAVITY[0]


# ---------------------------------------------------------------- confidence ----


async def test_confidence_is_the_mean_of_the_deciding_desks_only() -> None:
    signed = await DecisionDesk().adjudicate(
        [
            filed(Desk.TEXT, Determination.SUPPORTED, confidence=0.4),
            filed(Desk.FACT_CHECK, Determination.SUPPORTED, confidence=0.8),
            # Not deciding, and very sure of itself. It must not reach the number.
            filed(Desk.AUDIO, Determination.CLEAR, confidence=1.0),
        ]
    )
    assert signed.verdict.confidence == pytest.approx(0.6)


async def test_nothing_here_averages_determinations_together() -> None:
    """Two desks either side of the scale do not meet in the middle."""
    signed = await DecisionDesk().adjudicate(
        [
            filed(Desk.TEXT, Determination.SUPPORTED, confidence=0.9),
            filed(Desk.FACT_CHECK, Determination.CONTRADICTED, confidence=0.9),
        ]
    )
    assert signed.verdict.determination is Determination.CONTRADICTED
    assert signed.verdict.confidence == pytest.approx(0.9)


# ------------------------------------------------------------- what it files ----


async def test_the_rationale_quotes_the_deciding_desk_and_lists_the_rest() -> None:
    signed = await DecisionDesk().adjudicate(
        [
            filed(Desk.FACT_CHECK, Determination.CONTRADICTED),
            filed(Desk.TEXT, Determination.CLEAR),
        ]
    )
    rationale = signed.verdict.rationale
    assert "the fact-check desk filed CONTRADICTED" in rationale
    assert "What the fact-check desk found." in rationale
    assert "Also on the record: the text desk filed CLEAR." in rationale


async def test_a_unanimous_record_lists_no_others() -> None:
    signed = await DecisionDesk().adjudicate(
        [
            filed(Desk.TEXT, Determination.CLEAR),
            filed(Desk.IMAGE, Determination.CLEAR),
        ]
    )
    assert "the text desk and the image desk filed CLEAR" in signed.verdict.rationale
    assert "Also on the record" not in signed.verdict.rationale


async def test_the_headline_is_restated_and_not_borrowed() -> None:
    """A record carrying two desks' findings is not titled as though it carried one."""
    reports = [filed(Desk.TEXT, Determination.SUPPORTED)]
    signed = await DecisionDesk().adjudicate(reports)
    assert signed.verdict.headline == HEADLINES[Determination.SUPPORTED]
    assert signed.verdict.headline != reports[0].verdict.headline


async def test_every_report_gets_a_ledger_row_and_a_signal() -> None:
    reports = [
        filed(Desk.TEXT, Determination.CLEAR, confidence=0.5),
        filed(Desk.FACT_CHECK, Determination.SUPPORTED, confidence=0.62),
    ]
    signed = await DecisionDesk().adjudicate(reports)

    ledger = {entry.key: entry.value for entry in signed.ledger}
    assert ledger["Desks reporting"] == "2"
    assert ledger["Text desk"] == "CLEAR at 50%"
    assert ledger["Fact-check desk"] == "SUPPORTED at 62%"

    assert [(s.label, s.reading, s.weight) for s in signed.signals] == [
        ("Text desk", "CLEAR", 0.5),
        ("Fact-check desk", "SUPPORTED", 0.62),
    ]


async def test_it_merges_no_exhibits_or_annotations() -> None:
    """Refs are numbered from one per desk, so a merged list would carry several
    exhibit 1s and a reader following a citation would land on the wrong page."""
    signed = await DecisionDesk().adjudicate(
        [furnished(Desk.TEXT), furnished(Desk.FACT_CHECK)]
    )
    assert signed.exhibits == ()
    assert signed.annotations == ()


async def test_it_signs_its_own_desk() -> None:
    signed = await DecisionDesk().adjudicate([canned(Desk.TEXT)])
    assert signed.desk is ADJUDICATOR


# ------------------------------------------------------------- nothing filed ----


async def test_no_reports_is_still_a_signed_record() -> None:
    """Every desk failed. A reader is better served by a record that says nothing was
    established than by one stuck with no verdict at all."""
    signed = await DecisionDesk().adjudicate([])
    assert signed.desk is ADJUDICATOR
    assert signed.verdict.determination is Determination.INSUFFICIENT
    assert signed.verdict.headline == NOTHING_FILED
    assert signed.verdict.confidence == 0.0
    assert signed.verdict.rationale != ""
    assert {entry.key: entry.value for entry in signed.ledger} == {
        "Desks reporting": "0"
    }
