"""Response envelopes shared across the API.

These are the shapes every endpoint agrees on. Domain schemas live beside the
feature that owns them; what belongs here is only what more than one feature — or
the error layer — has to speak.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    """The body of a failed response.

    ``code`` is the contract. It is a stable snake-case string that clients may
    branch on, which is why the message is kept separate: the message is written
    for a person and may be reworded at any time.
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="Stable machine-readable error identifier.")
    message: str = Field(description="Human-readable explanation. May change.")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured context for the error. Shape varies by code.",
    )
    request_id: str | None = Field(
        default=None,
        description="Correlation id for this request, for support and tracing.",
    )


class ErrorResponse(BaseModel):
    """Every non-2xx response from this API has this body."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail


def error_response(
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Build the serialised error body.

    Returns a plain ``dict`` rather than the model because it is handed straight
    to ``JSONResponse``, and going through the model only to dump it again buys
    nothing at the point of failure.
    """
    return ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            details=details or {},
            request_id=request_id,
        )
    ).model_dump(mode="json")
