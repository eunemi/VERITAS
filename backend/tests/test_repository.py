"""The in-memory verification store.

The eviction tests are the reason this file exists. A bounded store that evicted the
wrong record — or that reset a record's age every time a desk reported — would lose
verifications a client was still polling, and it would do so only under load, which
is where it would be hardest to notice.
"""

from __future__ import annotations

import pytest

from app.core.errors import NotFoundError
from app.domain import (
    ADJUDICATOR,
    Artifact,
    ArtifactKind,
    Desk,
    DeskReport,
    Determination,
    Failure,
    Status,
    Verdict,
    Verification,
)
from app.repositories import MAX_RECORDS, InMemoryVerificationRepository


@pytest.fixture
def store() -> InMemoryVerificationRepository:
    return InMemoryVerificationRepository()


def submission(content: str = "copy") -> Verification:
    return Verification.submitted(
        artifact=Artifact(kind=ArtifactKind.TEXT, content=content),
        desks=(Desk.TEXT,),
    )


def report(desk: Desk = Desk.TEXT) -> DeskReport:
    return DeskReport(
        desk=desk,
        verdict=Verdict(
            determination=Determination.SUPPORTED,
            headline="Checked",
            rationale="Two records agree.",
            confidence=0.9,
        ),
    )


async def test_a_created_record_reads_back(store: InMemoryVerificationRepository) -> None:
    record = submission()
    await store.create(record)

    assert await store.get(record.id) == record


async def test_an_unknown_id_reads_as_none(store: InMemoryVerificationRepository) -> None:
    """`None` rather than a raise: turning absence into a 404 is the service's call."""
    assert await store.get("nope") is None


async def test_the_full_transition_sequence(store: InMemoryVerificationRepository) -> None:
    record = submission()
    await store.create(record)

    await store.mark_running(record.id)
    await store.start_desk(record.id, Desk.TEXT)
    await store.add_report(record.id, report())
    await store.start_desk(record.id, ADJUDICATOR)
    await store.add_report(record.id, report(ADJUDICATOR))
    await store.complete(record.id)

    stored = await store.get(record.id)
    assert stored is not None
    assert stored.status is Status.COMPLETED
    assert len(stored.reports) == 2
    assert stored.verdict is not None
    assert all(p.status is Status.COMPLETED for p in stored.desks)


async def test_failing_is_recorded(store: InMemoryVerificationRepository) -> None:
    record = submission()
    await store.create(record)

    await store.fail(record.id, Failure(code="not_implemented", message="No desk.", desk=Desk.TEXT))

    stored = await store.get(record.id)
    assert stored is not None
    assert stored.status is Status.FAILED
    assert stored.failure is not None
    assert stored.failure.code == "not_implemented"


@pytest.mark.parametrize(
    "write",
    [
        lambda s: s.mark_running("nope"),
        lambda s: s.start_desk("nope", Desk.TEXT),
        lambda s: s.add_report("nope", report()),
        lambda s: s.complete("nope"),
        lambda s: s.fail("nope", Failure(code="internal_error", message="x")),
    ],
)
async def test_every_write_to_an_unknown_id_raises(
    store: InMemoryVerificationRepository, write
) -> None:
    """Unlike a read. A write against a record that is not there is a bug in the
    caller, and silently succeeding would hide it."""
    with pytest.raises(NotFoundError):
        await write(store)


async def test_records_do_not_leak_between_stores() -> None:
    """One store per application, which is what lets two apps coexist in one test
    session without seeing each other's records."""
    first, second = InMemoryVerificationRepository(), InMemoryVerificationRepository()
    record = submission()
    await first.create(record)

    assert await second.get(record.id) is None


async def test_the_store_is_bounded() -> None:
    """The bound is injectable so this does not have to create a thousand records."""
    store = InMemoryVerificationRepository(max_records=3)
    oldest = submission("first")
    await store.create(oldest)
    for index in range(3):
        await store.create(submission(f"filler-{index}"))

    assert await store.get(oldest.id) is None


async def test_the_default_bound_is_the_exported_one() -> None:
    assert InMemoryVerificationRepository()._max_records == MAX_RECORDS


async def test_reporting_does_not_reset_a_record_s_age() -> None:
    """A verification's age is when it was submitted, not when a desk last reported.

    If a write moved a record to the young end, a long-running examination would keep
    itself alive by making progress and evict records that had merely been waiting —
    so the store would drop whichever verifications were quietest, not oldest.
    """
    store = InMemoryVerificationRepository(max_records=3)
    oldest = submission("first")
    await store.create(oldest)
    younger = submission("second")
    await store.create(younger)

    # Touch the oldest record repeatedly, then push the store past its bound.
    await store.mark_running(oldest.id)
    await store.start_desk(oldest.id, Desk.TEXT)
    await store.create(submission("third"))
    await store.create(submission("fourth"))

    assert await store.get(oldest.id) is None
    assert await store.get(younger.id) is not None
