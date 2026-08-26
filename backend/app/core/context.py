"""Per-request context.

The request id has to reach a log record emitted deep inside a pipeline without
being threaded through every function signature on the way down. A context
variable is the mechanism for that: :mod:`app.core.middleware` sets it at the
edge, and the log filter in :mod:`app.core.logging` reads it when formatting.

Kept in its own module because both logging and middleware need it, and importing
one from the other would make the cycle.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

#: Correlation id for the request being served on this task. Empty outside one.
_request_id: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the current request id, or an empty string if there is none."""
    return _request_id.get()


def set_request_id(request_id: str) -> Token[str]:
    """Bind ``request_id`` to this context; returns a token for :func:`reset`."""
    return _request_id.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    """Restore whatever request id was bound before ``token`` was issued."""
    _request_id.reset(token)
