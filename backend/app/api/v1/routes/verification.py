"""Verification routes: submit an artifact, read the record, list your own.

``POST /verify`` answers 202 and returns immediately; ``GET /verification/{id}`` is
polled until the record is terminal. The alternative — one request that blocks until
every desk has reported — would hold a connection open for the length of the
examination and give the caller nothing to show while it runs, and the frontend's
stage ticker exists precisely because there is progress worth reading.

**Authentication is optional on the first two and required on the third.** Submitting
without an account is a supported case, not a degraded one: the owner column is
nullable, and requiring a login to check a claim would put a registration form in
front of the thing this service is for. What signing in buys is ownership — a record
with an owner is readable only by that owner, and ``GET /verifications`` is the list
of them.

Neither handler contains a decision. They convert a validated request into a service
call and a domain record into a response; everything else is in
:class:`app.services.verification.VerificationService`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Path, Query, Response, status

from app.api.deps import (
    CurrentUserDep,
    OptionalUserDep,
    SettingsDep,
    VerificationServiceDep,
)
from app.api.responses import COMMON_ERRORS, error, set_poll_hint
from app.schemas.verification import (
    VerificationAccepted,
    VerificationHistoryOut,
    VerificationOut,
    VerifyRequest,
)
from app.services.verification import DEFAULT_HISTORY_LIMIT, MAX_HISTORY_LIMIT

router = APIRouter(tags=["verification"], responses=COMMON_ERRORS)


@router.post(
    "/verify",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=VerificationAccepted,
    summary="Submit an artifact for verification",
    responses={
        401: error("A bearer token was sent, but it is invalid or expired."),
        413: error("The artifact's text is longer than MAX_TEXT_CHARS."),
    },
)
async def submit_verification(
    payload: VerifyRequest,
    service: VerificationServiceDep,
    settings: SettingsDep,
    background: BackgroundTasks,
    response: Response,
    user: OptionalUserDep,
) -> VerificationAccepted:
    """Accept an artifact, open the desks on it, and return an id to poll.

    Answers ``202 Accepted`` with a ``Location`` header pointing at the record. The
    202 is not a hedge — the examination genuinely has not happened yet, and a 201
    would claim a finished resource exists.

    Sending a token attaches the record to that account, which makes it private to
    it and puts it in ``GET /verifications``. Sending none submits anonymously, and
    the id in the response is then the only handle on the record that exists.

    The response is built through ``response_model`` with the ``Location`` set on an
    injected ``Response``, rather than by returning a ``JSONResponse(headers=...)``.
    Returning a ``Response`` subclass makes FastAPI skip ``response_model`` entirely
    while the generated document goes on advertising it, so the two would silently
    drift apart.
    """
    artifact, desks = payload.to_domain()
    record = await service.submit(
        artifact=artifact, desks=desks, user_id=user.id if user else None
    )
    # Only the id crosses into the task. `service.run` is a bound method, and what it
    # closes over is the app-lifetime store on `app.state`, not a request-scoped
    # resource — which is the whole of the rule. FastAPI closes a `yield` dependency's
    # exit stack *before* the response is sent and background tasks run after, so a
    # per-request session handed to a task is already closed when the task uses it.
    # When the store becomes session-backed this stops being a BackgroundTask and
    # becomes a queue enqueue of `record.id`; `run(id)` is already that signature.
    background.add_task(service.run, record.id)
    response.headers["Location"] = (
        f"{settings.API_V1_PREFIX}/verification/{record.id}"
    )
    return VerificationAccepted.from_domain(record)


@router.get(
    "/verifications",
    response_model=VerificationHistoryOut,
    summary="List your own verifications",
    responses={401: error("Missing, invalid, or expired bearer token.")},
)
async def read_history(
    service: VerificationServiceDep,
    user: CurrentUserDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_HISTORY_LIMIT,
            description="How many of the most recent records to return.",
        ),
    ] = DEFAULT_HISTORY_LIMIT,
) -> VerificationHistoryOut:
    """Return the caller's verifications, newest first.

    Authentication is required rather than optional, because there is no such thing
    as an anonymous caller's history: an anonymous submission has no owner to match
    on, and its id is the only handle on it.

    The account comes from the token and there is no path or query parameter naming
    a user, so there is no version of this request that asks for somebody else's
    records.
    """
    records = await service.history(user_id=user.id, limit=limit)
    return VerificationHistoryOut.from_domain(records)


@router.get(
    "/verification/{verification_id}",
    response_model=VerificationOut,
    summary="Read a verification",
    responses={
        401: error("A bearer token was sent, but it is invalid or expired."),
        404: error("No verification with that id, or it belongs to somebody else."),
    },
)
async def read_verification(
    verification_id: Annotated[
        str, Path(description="The id returned by POST /verify.")
    ],
    service: VerificationServiceDep,
    response: Response,
    user: OptionalUserDep,
) -> VerificationOut:
    """Return the record as it stands, whether or not the desks have finished.

    A record submitted with a token is readable only by that account, and anyone
    else — including an anonymous caller — gets 404 rather than 403. The service
    explains why that is a 404; the short version is that a 403 would confirm the id
    exists. An anonymous record has no owner and stays readable by id, which is what
    lets the client that submitted it poll without signing in.

    Always the same shape. A pending record has an empty ``reports`` list and every
    desk on ``pending``; a failed one keeps whatever reports were filed before the
    failure and adds ``failure``. A client renders one view and watches it fill in
    rather than switching on status to choose a response format.
    """
    record = await service.get(verification_id, viewer_id=user.id if user else None)
    set_poll_hint(response, record)
    return VerificationOut.from_domain(record)
