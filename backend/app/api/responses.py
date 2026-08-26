"""Shared OpenAPI response declarations and HTTP response conventions.

Two things live here, both properly the API layer's business rather than a
schema's or a service's: what a route promises in the generated document, and the
headers a route sets on the way out.

Declaring ``422`` explicitly is load-bearing, not decorative. FastAPI auto-documents
a 422 as ``HTTPValidationError`` — ``{"detail": [...]}`` — for any route that takes a
body, but this application returns ``{"error": {...}}`` for every non-2xx, because
:mod:`app.core.exception_handlers` replaces the default handler. Declaring 422 here
*replaces* the auto-injected entry rather than adding a second one, so the document
stops advertising a shape the API never sends.
"""

from __future__ import annotations

from typing import Any

from fastapi import Response

from app.domain import Verification
from app.schemas.common import ErrorResponse

#: How long a client is told to wait before polling a running verification again.
#: One second, and not configurable: it is a hint a client may ignore, the desks
#: take seconds rather than minutes, and a setting would imply the server knows
#: something about pacing that it does not.
POLL_INTERVAL_SECONDS = 1


def error(description: str) -> dict[str, Any]:
    """An OpenAPI response entry for this application's error envelope."""
    return {"model": ErrorResponse, "description": description}


#: Declared on every router that takes a body. Both of these are produced by
#: handlers in :mod:`app.core.exception_handlers`, so no route raises them.
COMMON_ERRORS: dict[int | str, dict[str, Any]] = {
    422: error("Well-formed JSON, but not a valid request."),
    500: error(
        "An unhandled error. The body's `request_id` matches the log line, and "
        "the response carries it in the X-Request-ID header."
    ),
}


def set_poll_hint(response: Response, record: Verification) -> None:
    """Add ``Retry-After`` while there is still something to wait for.

    Omitted once the verification is terminal, which is the useful half: a client
    that polls until the header stops appearing needs no knowledge of which statuses
    are final. The ``terminal`` field on the body says the same thing for a client
    that reads bodies rather than headers.

    ``Retry-After`` is not on the CORS response-header safelist, so it — like
    ``Location`` — has to be named in ``expose_headers`` or a browser reads ``null``.
    """
    if not record.status.is_terminal:
        response.headers["Retry-After"] = str(POLL_INTERVAL_SECONDS)
