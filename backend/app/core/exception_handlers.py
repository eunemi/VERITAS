"""Translation from exceptions to HTTP responses.

Registered once by :func:`app.main.create_app`. Four handlers cover everything:
the application's own hierarchy, FastAPI's request-validation failure, Starlette's
``HTTPException`` (raised by the framework itself for 404s and the like), and a
catch-all so an unexpected exception still returns the documented envelope rather
than an HTML traceback.

The catch-all is the reason this exists. Without it, a bug in a service leaks a
stack trace to the client in debug mode and an unformatted 500 otherwise; with
it, the trace goes to the log with a request id attached and the client gets a
body it can parse.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import get_request_id
from app.core.errors import VeritasError
from app.core.logging import get_logger
from app.schemas.common import error_response

logger = get_logger(__name__)


def _request_id_for(request: Request) -> str | None:
    """Resolve the correlation id to put in an error body.

    ``request.state`` is consulted before the context variable, because the
    catch-all handler runs inside Starlette's ``ServerErrorMiddleware``, which
    sits *outside* :class:`~app.core.middleware.RequestContextMiddleware` — by the
    time a 500 is rendered, the context variable has already been unbound. The id
    stashed on ``request.state`` survives, because that state lives in the ASGI
    scope and every ``Request`` built from the same scope shares it.
    """
    return getattr(request.state, "request_id", "") or get_request_id() or None


def _render(
    request: Request,
    *,
    status: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    headers: dict[str, str] = {}
    origin = request.headers.get("origin")
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Access-Control-Expose-Headers"] = "X-Request-ID, Location, Retry-After"

    return JSONResponse(
        status_code=status,
        content=error_response(
            code=code,
            message=message,
            details=details,
            request_id=_request_id_for(request),
        ),
        headers=headers if headers else None,
    )


async def handle_veritas_error(request: Request, exc: Exception) -> JSONResponse:
    """Render a deliberate application failure."""
    assert isinstance(exc, VeritasError)  # guaranteed by the registration below

    # A 5xx from our own hierarchy is a fault worth a stack trace; a 4xx is the
    # client being told something and only worth a line.
    if exc.status >= HTTPStatus.INTERNAL_SERVER_ERROR:
        logger.error(
            "application error",
            exc_info=exc,
            extra={"error_code": exc.code, "path": request.url.path},
        )
    else:
        logger.info(
            "request rejected",
            extra={
                "error_code": exc.code,
                "path": request.url.path,
                "status_code": exc.status,
            },
        )

    return _render(
        request,
        status=exc.status,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    """Render FastAPI's own request-validation failure in our envelope."""
    assert isinstance(exc, RequestValidationError)

    return _render(
        request,
        status=HTTPStatus.UNPROCESSABLE_ENTITY,
        code="validation_error",
        message="Request validation failed.",
        details={"errors": jsonable_errors(exc)},
    )


def jsonable_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Reduce pydantic's error list to the fields a client can act on.

    Pydantic's raw errors can carry a non-serialisable value in ``ctx`` (the
    offending input itself, an exception instance), which would fail while
    rendering the response. Only the three fields below are kept, all strings.
    """
    reduced: list[dict[str, Any]] = []
    for error in exc.errors():
        reduced.append(
            {
                # `loc` identifies the offending field path, e.g. ["body", "claim"].
                "field": ".".join(str(part) for part in error.get("loc", ())),
                "message": error.get("msg", ""),
                "type": error.get("type", ""),
            }
        )
    return reduced


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    """Render framework-raised ``HTTPException`` in our envelope."""
    assert isinstance(exc, StarletteHTTPException)

    try:
        code = HTTPStatus(exc.status_code).name.lower()
    except ValueError:
        # Non-standard status codes are legal; fall back rather than fail.
        code = "http_error"

    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return _render(request, status=exc.status_code, code=code, message=detail)


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Last resort. Log the trace, return the envelope, reveal nothing."""
    logger.exception(
        "unhandled exception",
        extra={"path": request.url.path, "method": request.method},
    )

    # Deliberately generic: the request id in the body is how this response gets
    # tied back to the logged trace, which is where the detail belongs.
    return _render(
        request,
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
        code="internal_error",
        message="An unexpected error occurred.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach every handler above to ``app``."""
    app.add_exception_handler(VeritasError, handle_veritas_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    # Registering against bare `Exception` is what installs the catch-all.
    app.add_exception_handler(Exception, handle_unexpected_error)
