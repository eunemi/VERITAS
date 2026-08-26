"""A PostgreSQL-backed verification store.

The same Protocol the in-memory store implements (:mod:`app.repositories.base`),
so choosing it is one line in :func:`app.main.create_app`. What differs is where
state lives and how a transition is applied.

Two things this store does that the in-memory one did not have to:

* **A session per method.** It holds an ``async_sessionmaker``, not an open
  ``AsyncSession``, and opens a short one inside each call. Every intent-named
  method is therefore one transaction, which is what lets ``run`` drive it from a
  background task — the route note in ``app/api/v1/routes/verification.py`` explains
  why a single request-scoped session cannot: FastAPI closes it before the task
  runs. Each write commits or rolls back on its own.

* **A transition applied in the store, not read-modify-written in Python.** The
  in-memory store called ``record.started()`` and replaced the whole object. Here
  the equivalent is an ``UPDATE`` of the columns that change. Rebuilding the whole
  aggregate to flip a status column would be the load-replace-overwrite the
  Protocol's method names exist to avoid.

The factory is resolved lazily — ``session_factory`` defaults to ``None`` and falls
back to :func:`app.database.session.get_session_factory` per call — because
``app = create_app()`` runs at import of :mod:`app.main`, and building the engine
eagerly there would require the async driver to be importable before anything runs.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import NotFoundError
from app.database.session import get_session_factory
from app.domain import (
    Artifact,
    ArtifactKind,
    Desk,
    DeskProgress,
    DeskReport,
    Failure,
    Status,
    Verification,
)
from app.models import DeskReportRow, DeskRow, VerificationRow
from app.repositories.sql import coding
from app.utils.clock import utcnow
from app.utils.ids import new_id


class SqlVerificationRepository:
    """Stores verifications in PostgreSQL and advances their state in place."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] | None = None
    ) -> None:
        self._session_factory = session_factory

    @property
    def _factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory or get_session_factory()

    async def create(self, verification: Verification) -> None:
        async with self._factory() as session:
            session.add(_to_row(verification))
            await session.commit()

    async def get(self, verification_id: str) -> Verification | None:
        async with self._factory() as session:
            row = await session.get(VerificationRow, verification_id)
            return _to_domain(row) if row is not None else None

    async def list_for_user(
        self, user_id: str, *, limit: int = 50
    ) -> tuple[Verification, ...]:
        async with self._factory() as session:
            # The owner is in the WHERE clause, so a row belonging to somebody else
            # is never fetched — not fetched and then dropped. `id` breaks ties on
            # `created_at` so that two verifications submitted in the same
            # millisecond come back in a stable order across pages.
            found = await session.execute(
                select(VerificationRow)
                .where(VerificationRow.user_id == user_id)
                .order_by(
                    VerificationRow.created_at.desc(), VerificationRow.id.desc()
                )
                .limit(limit)
            )
            return tuple(_to_domain(row) for row in found.scalars().all())

    async def mark_running(self, verification_id: str) -> None:
        async with self._factory() as session:
            row = await self._require(session, verification_id)
            moment = utcnow()
            row.status = Status.RUNNING
            row.updated_at = moment
            await session.commit()

    async def start_desk(self, verification_id: str, desk: Desk) -> None:
        async with self._factory() as session:
            row = await self._require(session, verification_id)
            moment = utcnow()
            for desk_row in row.desks:
                if desk_row.desk is desk:
                    desk_row.status = Status.RUNNING
                    desk_row.started_at = moment
            # A desk not on the roster is a no-op, matching the in-memory store,
            # so a failure recorded against the wrong desk still records the
            # failure rather than raising over the roster mismatch.
            row.updated_at = moment
            await session.commit()

    async def add_report(self, verification_id: str, report: DeskReport) -> None:
        async with self._factory() as session:
            row = await self._require(session, verification_id)
            moment = utcnow()
            row.reports.append(_report_row(report, position=len(row.reports)))
            for desk_row in row.desks:
                if desk_row.desk is report.desk:
                    desk_row.status = Status.COMPLETED
                    desk_row.completed_at = moment
            row.updated_at = moment
            await session.commit()

    async def complete(self, verification_id: str) -> None:
        async with self._factory() as session:
            row = await self._require(session, verification_id)
            moment = utcnow()
            row.status = Status.COMPLETED
            row.completed_at = moment
            row.updated_at = moment
            await session.commit()

    async def fail(self, verification_id: str, failure: Failure) -> None:
        async with self._factory() as session:
            row = await self._require(session, verification_id)
            moment = utcnow()
            row.status = Status.FAILED
            row.failure_code = failure.code
            row.failure_message = failure.message
            row.failure_desk = failure.desk
            # The desk to blame, if there is one, is marked failed; the reports
            # already filed stay, because they are the only record of how far the
            # examination got before it stopped.
            if failure.desk is not None:
                for desk_row in row.desks:
                    if desk_row.desk is failure.desk:
                        desk_row.status = Status.FAILED
                        desk_row.completed_at = moment
            row.completed_at = moment
            row.updated_at = moment
            await session.commit()

    async def _require(
        self, session: AsyncSession, verification_id: str
    ) -> VerificationRow:
        row = await session.get(VerificationRow, verification_id)
        if row is None:
            raise NotFoundError(
                f"No verification with id {verification_id}.",
                details={"verification_id": verification_id},
            )
        return row


# ------------------------------------------------- domain <-> row mapping ---


def _to_row(verification: Verification) -> VerificationRow:
    artifact = verification.artifact
    return VerificationRow(
        id=verification.id,
        user_id=verification.user_id,
        artifact_kind=artifact.kind,
        artifact_content=artifact.content,
        artifact_url=artifact.url,
        artifact_filename=artifact.filename,
        status=verification.status,
        failure_code=verification.failure.code if verification.failure else None,
        failure_message=(
            verification.failure.message if verification.failure else None
        ),
        failure_desk=verification.failure.desk if verification.failure else None,
        created_at=verification.created_at,
        updated_at=verification.updated_at,
        completed_at=verification.completed_at,
        desks=[
            DeskRow(
                desk=progress.desk,
                position=position,
                status=progress.status,
                started_at=progress.started_at,
                completed_at=progress.completed_at,
            )
            for position, progress in enumerate(verification.desks)
        ],
        reports=[
            _report_row(report, position=position)
            for position, report in enumerate(verification.reports)
        ],
    )


def _report_row(report: DeskReport, *, position: int) -> DeskReportRow:
    verdict = report.verdict
    return DeskReportRow(
        id=new_id(),
        desk=report.desk,
        position=position,
        determination=verdict.determination,
        headline=verdict.headline,
        rationale=verdict.rationale,
        confidence=verdict.confidence,
        ledger=coding.plain_all(report.ledger),
        annotations=coding.plain_all(report.annotations),
        signals=coding.plain_all(report.signals),
        exhibits=coding.plain_all(report.exhibits),
        detail=coding.dump_detail(report.detail),
        filed_at=utcnow(),
    )


def _to_domain(row: VerificationRow) -> Verification:
    return Verification(
        id=row.id,
        user_id=row.user_id,
        artifact=Artifact(
            kind=ArtifactKind(row.artifact_kind),
            content=row.artifact_content,
            url=row.artifact_url,
            filename=row.artifact_filename,
        ),
        desks=tuple(_desk_progress(desk_row) for desk_row in row.desks),
        status=Status(row.status),
        reports=tuple(_report(report_row) for report_row in row.reports),
        failure=_failure(row),
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
    )


def _desk_progress(row: DeskRow) -> DeskProgress:
    return DeskProgress(
        desk=Desk(row.desk),
        status=Status(row.status),
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _report(row: DeskReportRow) -> DeskReport:
    return DeskReport(
        desk=Desk(row.desk),
        verdict=coding.load_verdict(
            {
                "determination": row.determination,
                "headline": row.headline,
                "rationale": row.rationale,
                "confidence": row.confidence,
            }
        ),
        ledger=coding.load_ledger(row.ledger),
        annotations=coding.load_annotations(row.annotations),
        signals=coding.load_signals(row.signals),
        exhibits=coding.load_exhibits(row.exhibits),
        detail=coding.load_detail(row.detail),
    )


def _failure(row: VerificationRow) -> Failure | None:
    if row.failure_code is None:
        return None
    return Failure(
        code=row.failure_code,
        message=row.failure_message or "",
        desk=Desk(row.failure_desk) if row.failure_desk else None,
    )
