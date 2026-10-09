"""The domain: the desk-routing rule and the record's state transitions.

Tested directly, without HTTP, because these are the only two places in this task
where anything decides something. Everything above them is conversion.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.core.errors import ValidationError
from app.domain import (
    ADJUDICATOR,
    DEFAULT_DESKS,
    Artifact,
    ArtifactKind,
    Desk,
    DeskReport,
    Determination,
    Failure,
    Status,
    Verdict,
    Verification,
    can_examine,
    desks_for,
)

TEXT = Artifact(kind=ArtifactKind.TEXT, content="The bridge opened in March.")


def verdict(determination: Determination = Determination.SUPPORTED) -> Verdict:
    return Verdict(
        determination=determination,
        headline="Checked",
        rationale="Two independent records agree.",
        confidence=0.92,
    )


def report(desk: Desk) -> DeskReport:
    return DeskReport(desk=desk, verdict=verdict())


# ------------------------------------------------------------- desk routing ---


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (ArtifactKind.TEXT, (Desk.TEXT, Desk.FACT_CHECK)),
        (ArtifactKind.CLAIM, (Desk.TEXT, Desk.FACT_CHECK)),
        (ArtifactKind.URL, (Desk.TEXT, Desk.FACT_CHECK)),
        (ArtifactKind.IMAGE, (Desk.IMAGE,)),
    ],
)
def test_default_roster_per_kind(
    kind: ArtifactKind, expected: tuple[Desk, ...]
) -> None:
    assert desks_for(kind) == expected


def test_a_default_roster_is_in_the_same_order_a_requested_one_would_be() -> None:
    """Otherwise naming the desks explicitly gets a different verification.

    The orchestrator runs desks in the order it is handed and stops at the first
    that raises, and not every desk is built. So an unbuilt desk placed ahead of a
    built one in a default roster loses the built desk's report — while the same
    request naming both desks explicitly, normalised to declaration order, keeps it.
    Footage is the row this was wrong on.
    """
    for kind, roster in DEFAULT_DESKS.items():
        assert desks_for(kind, list(reversed(roster))) == roster


def test_every_kind_has_a_roster() -> None:
    """A kind with no entry would submit successfully and examine nothing."""
    assert set(DEFAULT_DESKS) == set(ArtifactKind)


def test_the_adjudicator_is_not_a_default_anywhere() -> None:
    """It is appended by `Verification.submitted`, not chosen by routing."""
    assert not any(ADJUDICATOR in roster for roster in DEFAULT_DESKS.values())


def test_can_examine_agrees_with_the_table() -> None:
    assert can_examine(Desk.FACT_CHECK, ArtifactKind.TEXT)
    assert not can_examine(Desk.FACT_CHECK, ArtifactKind.IMAGE)


def test_a_requested_roster_is_normalised() -> None:
    assert desks_for(ArtifactKind.TEXT, [Desk.FACT_CHECK, Desk.TEXT]) == (
        Desk.TEXT,
        Desk.FACT_CHECK,
    )


def test_duplicates_collapse() -> None:
    assert desks_for(ArtifactKind.TEXT, [Desk.TEXT, Desk.TEXT]) == (Desk.TEXT,)


def test_an_incompatible_desk_names_what_is_allowed() -> None:
    with pytest.raises(ValidationError) as caught:
        desks_for(ArtifactKind.IMAGE, [Desk.FACT_CHECK])

    assert caught.value.details == {
        "desk": "fact-check",
        "artifact_kind": "image",
        "allowed_desks": ["image"],
    }


def test_the_adjudicator_cannot_be_requested() -> None:
    with pytest.raises(ValidationError):
        desks_for(ArtifactKind.TEXT, [ADJUDICATOR])


def test_an_empty_roster_is_refused() -> None:
    """Distinct from `None`, which means "use the default"."""
    with pytest.raises(ValidationError):
        desks_for(ArtifactKind.TEXT, [])


# ------------------------------------------------------------------ verdict ---


@pytest.mark.parametrize("bad", [-0.1, 1.1, 42.0])
def test_confidence_outside_zero_to_one_is_refused(bad: float) -> None:
    with pytest.raises(ValueError):
        Verdict(
            determination=Determination.SUPPORTED,
            headline="h",
            rationale="r",
            confidence=bad,
        )


@pytest.mark.parametrize("edge", [0.0, 1.0])
def test_the_bounds_themselves_are_allowed(edge: float) -> None:
    assert (
        Verdict(
            determination=Determination.SUPPORTED,
            headline="h",
            rationale="r",
            confidence=edge,
        ).confidence
        == edge
    )


# ------------------------------------------------------------------ records ---


def test_submitting_appends_the_adjudicator() -> None:
    record = Verification.submitted(artifact=TEXT, desks=(Desk.TEXT, Desk.FACT_CHECK))

    assert [p.desk for p in record.desks] == [Desk.TEXT, Desk.FACT_CHECK, ADJUDICATOR]
    assert record.examining_desks == (Desk.TEXT, Desk.FACT_CHECK)
    assert record.status is Status.PENDING
    assert record.verdict is None


def test_two_submissions_get_different_ids() -> None:
    a = Verification.submitted(artifact=TEXT, desks=(Desk.TEXT,))
    b = Verification.submitted(artifact=TEXT, desks=(Desk.TEXT,))

    assert a.id != b.id


def test_a_record_is_immutable() -> None:
    """Every transition returns a new record, so a caller cannot half-apply one."""
    record = Verification.submitted(artifact=TEXT, desks=(Desk.TEXT,))

    with pytest.raises(dataclasses.FrozenInstanceError):
        record.status = Status.COMPLETED  # type: ignore[misc]


def test_filing_a_report_also_closes_that_desk() -> None:
    """One method for both, because a record holding a report from a desk it still
    believes is reading is a state no caller should be able to produce."""
    record = Verification.submitted(artifact=TEXT, desks=(Desk.TEXT,))

    record = record.started().desk_started(Desk.TEXT).with_report(report(Desk.TEXT))

    progress = {p.desk: p.status for p in record.desks}
    assert progress[Desk.TEXT] is Status.COMPLETED
    assert record.report_for(Desk.TEXT) is not None
    assert record.desks[0].started_at is not None
    assert record.desks[0].completed_at is not None


def test_the_verdict_is_read_out_of_the_decision_report() -> None:
    """Not stored twice. An examining desk's report does not set it."""
    record = Verification.submitted(artifact=TEXT, desks=(Desk.TEXT,))

    record = record.with_report(report(Desk.TEXT))
    assert record.verdict is None

    record = record.with_report(
        DeskReport(desk=ADJUDICATOR, verdict=verdict(Determination.CONTESTED))
    )
    assert record.verdict is not None
    assert record.verdict.determination is Determination.CONTESTED


def test_completing_sets_a_completion_time_and_clears_nothing_else() -> None:
    record = Verification.submitted(artifact=TEXT, desks=(Desk.TEXT,))
    record = record.with_report(report(Desk.TEXT)).completed()

    assert record.status is Status.COMPLETED
    assert record.status.is_terminal
    assert record.completed_at is not None
    assert record.failure is None
    assert len(record.reports) == 1


def test_failing_keeps_the_reports_already_filed() -> None:
    """A record that discarded them would lose the only evidence of how far it got."""
    record = Verification.submitted(artifact=TEXT, desks=(Desk.TEXT, Desk.FACT_CHECK))
    record = record.with_report(report(Desk.TEXT))

    record = record.failed(
        Failure(
            code="provider_error", message="The search timed out.", desk=Desk.FACT_CHECK
        )
    )

    assert record.status is Status.FAILED
    assert record.status.is_terminal
    assert len(record.reports) == 1
    progress = {p.desk: p.status for p in record.desks}
    assert progress[Desk.TEXT] is Status.COMPLETED
    assert progress[Desk.FACT_CHECK] is Status.FAILED
    assert progress[ADJUDICATOR] is Status.PENDING


def test_a_failure_with_no_desk_leaves_the_roster_alone() -> None:
    """Not every failure belongs to a desk — the store can break before one opens."""
    record = Verification.submitted(artifact=TEXT, desks=(Desk.TEXT,))

    record = record.failed(Failure(code="internal_error", message="Stopped."))

    assert record.failure is not None
    assert record.failure.desk is None
    assert all(p.status is Status.PENDING for p in record.desks)


def test_a_desk_not_on_the_roster_is_ignored() -> None:
    """Advancing an absent desk is a no-op rather than a crash, so a failure recorded
    against the wrong desk still records the failure."""
    record = Verification.submitted(artifact=TEXT, desks=(Desk.TEXT,))

    advanced = record.desk_started(Desk.IMAGE)

    assert [p.desk for p in advanced.desks] == [Desk.TEXT, ADJUDICATOR]
    assert all(p.status is Status.PENDING for p in advanced.desks)


def test_updated_at_moves_with_every_transition() -> None:
    record = Verification.submitted(artifact=TEXT, desks=(Desk.TEXT,))

    advanced = record.started()

    assert advanced.updated_at >= record.updated_at
    assert advanced.created_at == record.created_at


@pytest.mark.parametrize(
    ("status", "terminal"),
    [
        (Status.PENDING, False),
        (Status.RUNNING, False),
        (Status.COMPLETED, True),
        (Status.FAILED, True),
    ],
)
def test_which_statuses_end_the_polling(status: Status, terminal: bool) -> None:
    assert status.is_terminal is terminal


def test_media_is_recognised_as_media() -> None:
    assert Artifact(kind=ArtifactKind.IMAGE, url="https://a.test/c.png").is_media
    assert not TEXT.is_media
