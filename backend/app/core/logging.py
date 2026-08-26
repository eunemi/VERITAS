"""Logging setup.

One entry point, :func:`configure_logging`, called once from the application
factory. It installs a single handler on the root logger and routes uvicorn's own
loggers through it, so every line the process emits — framework or application —
has the same shape and the same request id.

Two formats: ``json`` for anywhere logs are collected by a machine, ``console``
for a terminal. Choosing between them is configuration, not a code branch at the
call site.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Literal

from app.core.context import get_request_id

#: Attributes present on every ``LogRecord``. Anything outside this set was
#: passed as ``extra=`` by the caller and belongs in the structured output.
_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class RequestIdFilter(logging.Filter):
    """Attach the current request id to every record.

    A filter rather than formatter logic so that both formatters, and any handler
    added later, see the field without repeating the lookup.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    """Return the caller-supplied ``extra`` fields on ``record``."""
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _RESERVED and not key.startswith("_")
    }


class JsonFormatter(logging.Formatter):
    """One JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = getattr(record, "request_id", "")
        if request_id:
            payload["request_id"] = request_id

        payload.update(_extras(record))

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        # `default=str` keeps a stray non-serialisable value in `extra` from
        # turning a log call into a second, more confusing exception.
        return json.dumps(payload, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Readable single line for a terminal, with the request id in brackets."""

    _FMT = "%(asctime)s %(levelname)-8s %(name)s%(request_suffix)s — %(message)s"

    def __init__(self) -> None:
        super().__init__(fmt=self._FMT, datefmt="%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        request_id = getattr(record, "request_id", "")
        record.request_suffix = f" [{request_id}]" if request_id else ""

        base = super().format(record)
        extras = _extras(record)
        # `request_suffix` is ours, not the caller's; it is already in the line.
        extras.pop("request_suffix", None)
        extras.pop("request_id", None)
        if extras:
            rendered = " ".join(f"{k}={v!r}" for k, v in sorted(extras.items()))
            base = f"{base} ({rendered})"
        return base


def configure_logging(
    *,
    level: str = "INFO",
    log_format: Literal["json", "console"] = "json",
) -> None:
    """Install the process-wide logging configuration.

    Idempotent: existing root handlers are removed first, so calling this twice
    (an app factory in a test suite, say) does not double every line.
    """
    formatter: logging.Formatter = (
        JsonFormatter() if log_format == "json" else ConsoleFormatter()
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    for existing in root.handlers[:]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn ships its own handlers and formatters. Clearing them and letting
    # the records propagate to root is what puts startup and error lines in the
    # same format as application logs.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True

    # uvicorn.access is silenced rather than reformatted: RequestContextMiddleware
    # already emits one line per request with the correlation id and duration,
    # and it honours the paths that should not be logged at all. Leaving both on
    # means two lines per request and a health-check line the filter was written
    # to suppress.
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    access.disabled = True

    # SQLAlchemy's engine logger is controlled by DATABASE_ECHO; keep it from
    # also inheriting DEBUG from the root level and logging every statement.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a module logger. Thin wrapper, kept so call sites import from here."""
    return logging.getLogger(name)
