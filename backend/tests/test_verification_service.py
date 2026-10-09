"""The orchestration in :class:`VerificationService`.

Everything here needs a desk, and no desk exists — so these tests register stubs from
:mod:`tests.stubs` for their own duration. What is under test is the sequence the
service drives, which is untestable otherwise, and which is where the mistakes that
matter live: a record left on ``pending``, a report filed against a desk still marked
reading, an adjudicator handed a stale copy of the reports.

The failure tests are the important half. ``run`` is a background task, so an
exception escaping it cannot be rendered — the response has already been sent — and
the only visible symptom would be a record stuck on ``pending`` forever.
"""

from __future__ import annotations

import inspect

import pytest

from app.core.errors import NotFoundError, PayloadTooLargeError, ProviderError
from app.desks.base import Adjudicator
from app.domain import (
    ADJUDICATOR,
    Artifact,
    ArtifactKind,
    Desk,
    Determination,
    Failure,
    Status,
)
from app.repositories import InMemoryVerificationRepository
from app.services.verification import VerificationService
from tests.stubs import StubAdjudicator, StubExaminer, desk_bench

TEXT = Artifact(kind=ArtifactKind.TEXT, content="The bridge opened in March.")


@pytest.fixture
def store() -> InMemoryVerificationRepository:
    return InMemoryVerificationRepository()


@pytest.fixture
def service(store: InMemoryVerificationRepository, settings) -> VerificationService:
    return VerificationService(repository=store, settings=settings)


# ------------------------------------------------------------------ submit ---


async def test_submit_persists_a_pending_record(
    service: VerificationService, store: InMemoryVerificationRepository
) -> None:
    record = await service.submit(artifact=TEXT, desks=(Desk.TEXT,))

    assert record.status is Status.PENDING
    assert await store.get(record.id) == record


async def test_submit_refuses_text_over_the_limit(
    store: InMemoryVerificationRepository, settings
) -> None:
    """The ceiling is enforced in the service, so a worker hits it too."""
    service = VerificationService(
        repository=store, settings=settings.model_copy(update={"MAX_TEXT_CHARS": 10})
    )

    with pytest.raises(PayloadTooLargeError):
        await service.submit(
            artifact=Artifact(kind=ArtifactKind.TEXT, content="x" * 20),
            desks=(Desk.TEXT,),
        )


async def test_get_turns_absence_into_a_not_found(service: VerificationService) -> None:
    """The store returns `None`; deciding that is a 404 is the service's call."""
    with pytest.raises(NotFoundError):
        await service.get("nope")


# --------------------------------------------------------------- happy path ---


async def test_a_full_run_reaches_completed(service: VerificationService) -> None:
    stubs = {
        Desk.TEXT: StubExaminer(Desk.TEXT),
        Desk.FACT_CHECK: StubExaminer(Desk.FACT_CHECK),
    }
    record = await service.submit(artifact=TEXT, desks=(Desk.TEXT, Desk.FACT_CHECK))

    with desk_bench(stubs, StubAdjudicator()):
        await service.run(record.id)

    finished = await service.get(record.id)
    assert finished.status is Status.COMPLETED
    assert finished.completed_at is not None
    assert finished.failure is None
    assert [r.desk for r in finished.reports] == [
        Desk.TEXT,
        Desk.FACT_CHECK,
        ADJUDICATOR,
    ]
    assert all(p.status is Status.COMPLETED for p in finished.desks)


async def test_every_desk_gets_the_artifact(service: VerificationService) -> None:
    stubs = {
        Desk.TEXT: StubExaminer(Desk.TEXT),
        Desk.FACT_CHECK: StubExaminer(Desk.FACT_CHECK),
    }
    record = await service.submit(artifact=TEXT, desks=(Desk.TEXT, Desk.FACT_CHECK))

    with desk_bench(stubs, StubAdjudicator()):
        await service.run(record.id)

    assert stubs[Desk.TEXT].seen == [TEXT]
    assert stubs[Desk.FACT_CHECK].seen == [TEXT]


async def test_the_adjudicator_sees_the_reports_as_filed(
    service: VerificationService,
) -> None:
    """The service re-reads the record before adjudicating.

    Its in-hand copy predates every report, so passing that copy's ``reports`` would
    hand the adjudicator an empty sequence and it would sign a verdict having read
    nothing — a bug that leaves a completed, plausible-looking record behind.
    """
    decision = StubAdjudicator()
    stubs = {
        Desk.TEXT: StubExaminer(Desk.TEXT),
        Desk.FACT_CHECK: StubExaminer(Desk.FACT_CHECK),
    }
    record = await service.submit(artifact=TEXT, desks=(Desk.TEXT, Desk.FACT_CHECK))

    with desk_bench(stubs, decision):
        await service.run(record.id)

    assert [r.desk for r in decision.seen[0]] == [Desk.TEXT, Desk.FACT_CHECK]


async def test_the_adjudicator_is_not_given_the_artifact() -> None:
    """The seam cannot hand it one.

    ``desks.ts`` states that the decision core "Does not: Re-examine the artifact
    itself", so ``adjudicate`` takes reports and nothing else. A signature that
    accepted an artifact would permit exactly what the desk is defined not to do.
    """
    params = inspect.signature(Adjudicator.adjudicate).parameters

    assert list(params) == ["self", "reports"]


async def test_the_verdict_comes_from_the_adjudicator(
    service: VerificationService,
) -> None:
    record = await service.submit(artifact=TEXT, desks=(Desk.TEXT,))

    with desk_bench(
        {Desk.TEXT: StubExaminer(Desk.TEXT)},
        StubAdjudicator(determination=Determination.SYNTHETIC),
    ):
        await service.run(record.id)

    finished = await service.get(record.id)
    assert finished.verdict is not None
    assert finished.verdict.determination is Determination.SYNTHETIC


# ------------------------------------------------------------------ failure ---


async def test_a_desk_raising_is_recorded_against_that_desk(
    service: VerificationService,
) -> None:
    stub = StubExaminer(
        Desk.TEXT, raises=ProviderError("Upstream refused.", provider="openai")
    )
    record = await service.submit(artifact=TEXT, desks=(Desk.TEXT,))

    with desk_bench({Desk.TEXT: stub}, StubAdjudicator()):
        await service.run(record.id)

    failed = await service.get(record.id)
    assert failed.status is Status.FAILED
    assert failed.failure == Failure(
        code="provider_error", message="Upstream refused.", desk=Desk.TEXT
    )


async def test_an_unexpected_error_becomes_an_internal_failure(
    service: VerificationService,
) -> None:
    """A bare exception is caught too, and its message does not reach the record.

    ``run`` is a background task; an escaping exception would be swallowed by the ASGI
    machinery with the response already sent, leaving the record on ``pending``.
    """
    stub = StubExaminer(Desk.TEXT, raises=RuntimeError("boom"))
    record = await service.submit(artifact=TEXT, desks=(Desk.TEXT,))

    with desk_bench({Desk.TEXT: stub}, StubAdjudicator()):
        await service.run(record.id)

    failed = await service.get(record.id)
    assert failed.status is Status.FAILED
    assert failed.failure is not None
    assert failed.failure.code == "internal_error"
    assert "boom" not in failed.failure.message





async def test_a_missing_adjudicator_is_recorded_against_the_decision_desk(
    service: VerificationService,
) -> None:
    """The examiners can all report and the record still fail at the last step."""
    record = await service.submit(artifact=TEXT, desks=(Desk.TEXT,))

    with desk_bench({Desk.TEXT: StubExaminer(Desk.TEXT)}):
        await service.run(record.id)

    failed = await service.get(record.id)
    assert failed.status is Status.FAILED
    assert failed.failure is not None
    assert failed.failure.desk is ADJUDICATOR
    assert [r.desk for r in failed.reports] == [Desk.TEXT]


async def test_earlier_reports_survive_a_later_failure(
    service: VerificationService,
) -> None:
    stubs = {
        Desk.TEXT: StubExaminer(Desk.TEXT),
        Desk.FACT_CHECK: StubExaminer(
            Desk.FACT_CHECK, raises=ProviderError("No.", provider="tavily")
        ),
    }
    record = await service.submit(artifact=TEXT, desks=(Desk.TEXT, Desk.FACT_CHECK))

    with desk_bench(stubs, StubAdjudicator()):
        await service.run(record.id)

    failed = await service.get(record.id)
    assert [r.desk for r in failed.reports] == [Desk.TEXT]
    progress = {p.desk: p.status for p in failed.desks}
    assert progress[Desk.TEXT] is Status.COMPLETED
    assert progress[Desk.FACT_CHECK] is Status.FAILED


async def test_a_vanished_record_is_not_an_error(service: VerificationService) -> None:
    """Evicted between submission and scheduling. There is nothing to advance and
    nowhere to record a failure, so ``run`` says so in the log and returns."""
    await service.run("nope")


async def test_a_broken_store_does_not_escape_the_task(settings) -> None:
    """The last statement of a background task cannot raise usefully.

    If recording the failure fails too, both the failure and the traceback would be
    lost in the ASGI machinery — so it is logged and dropped instead.
    """

    class BrokenOnWrite(InMemoryVerificationRepository):
        async def mark_running(self, verification_id: str) -> None:
            raise OSError("the disk is gone")

        async def fail(self, verification_id: str, failure: Failure) -> None:
            raise OSError("the disk is gone")

    service = VerificationService(repository=BrokenOnWrite(), settings=settings)
    record = await service.submit(artifact=TEXT, desks=(Desk.TEXT,))

    await service.run(record.id)  # must not raise
