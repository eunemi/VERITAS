"""Submitting, running and reading verifications.

Orchestration lives here rather than in a separate pipeline package. The service
already owns the record's state transitions, and giving a second component the
power to advance them would mean deciding, every time, which of the two is
authoritative.

The split between :meth:`VerificationService.submit` and
:meth:`VerificationService.run` is what makes the API's 202 honest: submit
persists and returns, run does the work. ``run`` takes an id and nothing else, so
the same method is already the signature a task queue or a ``python -m`` script
would call. Nothing about it knows it was scheduled by FastAPI.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.errors import NotFoundError, VeritasError
from app.core.logging import get_logger
from app.desks import get_adjudicator, get_examiner
from app.domain import (
    ADJUDICATOR,
    Artifact,
    Desk,
    Failure,
    Verification,
)
from app.repositories.base import VerificationRepository
from app.services.limits import ensure_within_limit

logger = get_logger(__name__)

#: How many past verifications a history request returns when it does not say.
DEFAULT_HISTORY_LIMIT = 20

#: The most any history request can ask for. A ceiling rather than a page size,
#: because a verification carries every report it has and a caller asking for a
#: thousand of them would be asking the store for a very large answer.
MAX_HISTORY_LIMIT = 100


class VerificationService:
    """The one place a verification is created, advanced, and read."""

    def __init__(
        self,
        *,
        repository: VerificationRepository,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._settings = settings

    # -------------------------------------------------------------- submit ---

    async def submit(
        self,
        *,
        artifact: Artifact,
        desks: tuple[Desk, ...],
        user_id: str | None = None,
    ) -> Verification:
        """Persist a pending verification and return it.

        Fast by design: it validates, writes one record and returns, so the
        endpoint can answer 202 without waiting on a desk. ``desks`` is the
        examining roster already resolved and validated by
        :func:`app.domain.desks_for`; the adjudicator is appended by
        :meth:`Verification.submitted`.

        ``user_id`` is the submitter when there was one. It is optional because an
        anonymous submission is a supported case, not a degraded one — the column is
        nullable for that reason. What an owner buys is the ownership rule in
        :meth:`get` and a place in :meth:`history`.
        """
        if artifact.content is not None:
            ensure_within_limit(
                artifact.content,
                limit=self._settings.MAX_TEXT_CHARS,
                field="artifact.content",
            )
        record = Verification.submitted(artifact=artifact, desks=desks, user_id=user_id)
        await self._repository.create(record)
        logger.info(
            "verification submitted",
            extra={
                "verification_id": record.id,
                "artifact_kind": artifact.kind.value,
                "desks": [p.desk.value for p in record.desks],
                "user_id": user_id,
            },
        )
        return record

    # ---------------------------------------------------------------- read ---

    async def get(
        self, verification_id: str, *, viewer_id: str | None = None
    ) -> Verification:
        """Return a verification the caller is allowed to read.

        The repository returns ``None`` for an unknown id; turning that into a 404
        is a decision about the API, so it is made here rather than in the store.
        """
        record = await self._require(verification_id)
        if record.user_id is not None and record.user_id != viewer_id:
            # Somebody else's record is reported as absent, not as forbidden. A 403
            # confirms the id exists, which turns this endpoint into an oracle for
            # anyone walking the id space; 404 says the same thing to the owner and
            # nothing to anyone else. An unowned record stays readable by id, which
            # is what keeps an anonymous submission pollable by the client that made
            # it.
            raise NotFoundError(
                f"No verification with id {verification_id}.",
                details={"verification_id": verification_id},
            )
        return record

    async def history(
        self, *, user_id: str, limit: int = DEFAULT_HISTORY_LIMIT
    ) -> tuple[Verification, ...]:
        """The caller's own verifications, newest first.

        ``user_id`` is not a filter this method applies — it is the argument to a
        store method that cannot return anything else. See
        :meth:`app.repositories.base.VerificationRepository.list_for_user`.
        """
        return await self._repository.list_for_user(
            user_id, limit=min(max(limit, 1), MAX_HISTORY_LIMIT)
        )

    # ----------------------------------------------------------------- run ---

    async def run(self, verification_id: str) -> None:
        """Examine the artifact, adjudicate, and close the record.

        Every exception is caught and recorded as a failed verification. This is
        not defensive habit — it is required. When this runs as a background task
        the response has already been sent, so Starlette's exception middleware
        hits its "response already started" guard and the handlers registered in
        :mod:`app.core.exception_handlers` cannot render anything. An escaping
        exception would therefore produce a logged traceback and a record stuck on
        ``pending`` forever, which is the exact outcome recording the failure
        exists to prevent.

        A desk that raises stops the run, and the adjudicator is not asked. The
        reports already filed are kept, so the record shows what was found before
        the break — but it is recorded as failed rather than signed, because a
        determination reached without one of the desks the roster promised is not
        the determination the roster describes.
        """
        desk: Desk | None = None
        try:
            record = await self._repository.get(verification_id)
            if record is None:
                # Evicted between submission and scheduling. Nothing to advance
                # and nowhere to record a failure, so say so and stop.
                logger.warning(
                    "verification vanished before it ran",
                    extra={"verification_id": verification_id},
                )
                return

            await self._repository.mark_running(verification_id)

            for desk in record.examining_desks:
                await self._repository.start_desk(verification_id, desk)
                report = await get_examiner(desk).examine(
                    record.artifact, verification_id=verification_id
                )
                await self._repository.add_report(verification_id, report)

            desk = ADJUDICATOR
            await self._repository.start_desk(verification_id, desk)
            # Re-read: the adjudicator weighs the reports as filed, and the
            # in-hand copy predates all of them. Through `_require` and not `get`,
            # because the examination is not a viewer — an owned record must not
            # become unreadable to the worker running it.
            filed = await self._require(verification_id)
            decision = await get_adjudicator(desk).adjudicate(filed.reports)
            await self._repository.add_report(verification_id, decision)

            await self._repository.complete(verification_id)
            logger.info(
                "verification completed", extra={"verification_id": verification_id}
            )
        except VeritasError as exc:
            logger.warning(
                "verification failed",
                extra={
                    "verification_id": verification_id,
                    "error_code": exc.code,
                    "desk": desk.value if desk else None,
                },
            )
            await self._record_failure(
                verification_id, Failure(code=exc.code, message=exc.message, desk=desk)
            )
        except Exception:
            logger.exception(
                "verification raised an unexpected error",
                extra={
                    "verification_id": verification_id,
                    "desk": desk.value if desk else None,
                },
            )
            await self._record_failure(
                verification_id,
                Failure(
                    code="internal_error",
                    message="The examination stopped on an unexpected error.",
                    desk=desk,
                ),
            )

    async def _require(self, verification_id: str) -> Verification:
        """Fetch by id with no ownership rule applied.

        The unguarded read. Callers that serve a request must go through
        :meth:`get`; this exists for the examination itself, which acts on the
        record rather than on behalf of a viewer.
        """
        record = await self._repository.get(verification_id)
        if record is None:
            raise NotFoundError(
                f"No verification with id {verification_id}.",
                details={"verification_id": verification_id},
            )
        return record

    async def _record_failure(self, verification_id: str, failure: Failure) -> None:
        """Write the failure, and swallow anything that goes wrong doing so.

        This is the last statement of a background task. An exception raised here
        escapes into the ASGI machinery with a response already sent, which loses
        both the failure and the traceback — so a store that has evicted the
        record, or broken outright, is logged and dropped rather than raised.
        """
        try:
            await self._repository.fail(verification_id, failure)
        except Exception:
            logger.exception(
                "could not record a verification failure",
                extra={"verification_id": verification_id, "error_code": failure.code},
            )
