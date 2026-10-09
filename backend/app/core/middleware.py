"""HTTP middleware.

Two concerns, both of which have to sit at the outermost edge of the stack:
giving every request a correlation id, and recording one access line per request
once its duration is known.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.context import reset_request_id, set_request_id
from app.core.logging import get_logger
from app.utils.ids import new_request_id

logger = get_logger(__name__)

#: Inbound and outbound header carrying the correlation id.
REQUEST_ID_HEADER = "X-Request-ID"

#: Paths that should not produce an access log line. Health is polled on a short
#: interval by orchestrators; logging it buries everything else.
_UNLOGGED_PATHS = frozenset({"/health", "/metrics"})


class ContentLengthLimitMiddleware(BaseHTTPMiddleware):
    """Reject declared oversized request bodies before FastAPI parses them.

    Application-level schema limits are still needed for text fields, but they
    happen after the ASGI server has accepted and decoded the JSON. This small
    guard prevents ordinary browser and proxy requests with an oversized
    ``Content-Length`` from reaching that work. A reverse proxy must also set a
    body limit for chunked requests, whose size cannot be known from a header.
    """

    def __init__(self, app: object, *, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > self.max_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "payload_too_large",
                        "message": (
                            "The request body exceeds the configured size limit."
                        ),
                        "details": {"bytes": int(declared), "limit": self.max_bytes},
                        "request_id": getattr(request.state, "request_id", None),
                    }
                },
            )
        return await call_next(request)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a request id for the duration of the request and echo it back.

    An id supplied by the caller is honoured so a trace started at the frontend,
    or at an ingress, stays a single trace. It is length-capped because it is
    attacker-controlled and ends up in every log line for the request.
    """

    #: Generous enough for a UUID or a typical trace id, short enough that an
    #: oversized header cannot bloat the logs.
    MAX_INBOUND_LENGTH = 128

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        inbound = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request_id = inbound[: self.MAX_INBOUND_LENGTH] if inbound else new_request_id()

        token = set_request_id(request_id)
        # Handlers and dependencies read it from here rather than from the
        # context var when they already have the request in hand.
        request.state.request_id = request_id

        started = time.perf_counter()
        # Every log call below has to happen before the `finally` unbinds the id,
        # or the access line — the one line whose whole purpose is correlation —
        # comes out without one. Hence `else` rather than code after the block.
        try:
            response = await call_next(request)
        except Exception:
            # The exception handlers turn this into a response; this block exists
            # only so a failed request still produces a timed access line.
            duration_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "request failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                },
            )

            raise
        else:
            duration_ms = (time.perf_counter() - started) * 1000
            response.headers[REQUEST_ID_HEADER] = request_id

            if request.url.path not in _UNLOGGED_PATHS:
                logger.info(
                    "request completed",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "duration_ms": round(duration_ms, 2),
                    },
                )

            return response
        finally:
            reset_request_id(token)
