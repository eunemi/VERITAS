"""Logging: the formatters, and the correlation id reaching the access line."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.logging import ConsoleFormatter, JsonFormatter, RequestIdFilter
from app.core.middleware import REQUEST_ID_HEADER

MIDDLEWARE_LOGGER = "app.core.middleware"


@pytest.fixture
def captured() -> Iterator[list[logging.LogRecord]]:
    """Collect records from the middleware logger.

    A handler attached here rather than pytest's ``caplog``, because
    ``configure_logging`` clears root handlers when the application is built and
    would remove caplog's. The ``RequestIdFilter`` is attached for the same reason
    the real handler has one: it is what populates ``record.request_id``, and it
    reads the context variable at emit time — which is precisely what this test
    needs to observe.
    """
    records: list[logging.LogRecord] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = Collect(level=logging.DEBUG)
    handler.addFilter(RequestIdFilter())

    logger = logging.getLogger(MIDDLEWARE_LOGGER)
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)


def _lines(records: list[logging.LogRecord], message: str) -> list[logging.LogRecord]:
    return [record for record in records if record.getMessage() == message]


async def test_access_line_carries_the_request_id(
    app: FastAPI, client: AsyncClient, captured: list[logging.LogRecord]
) -> None:
    """Regression: the id must still be bound when the access line is emitted.

    The middleware resets the context variable in a ``finally``. If the log call
    sits after that block instead of inside it, every access line comes out with
    an empty request id — losing correlation on the one line whose entire purpose
    is correlation.
    """

    @app.get("/_test/ping")
    async def _ping() -> dict[str, bool]:
        return {"ok": True}

    await client.get("/_test/ping", headers={REQUEST_ID_HEADER: "trace-log"})

    completed = _lines(captured, "request completed")
    assert completed, "no access line was emitted"
    assert getattr(completed[0], "request_id", "") == "trace-log"


async def test_access_line_records_the_outcome(
    app: FastAPI, client: AsyncClient, captured: list[logging.LogRecord]
) -> None:
    @app.get("/_test/ping")
    async def _ping() -> dict[str, bool]:
        return {"ok": True}

    await client.get("/_test/ping")

    record = _lines(captured, "request completed")[0]
    assert record.method == "GET"  # type: ignore[attr-defined]
    assert record.path == "/_test/ping"  # type: ignore[attr-defined]
    assert record.status_code == 200  # type: ignore[attr-defined]
    assert record.duration_ms >= 0  # type: ignore[attr-defined]


async def test_health_is_not_access_logged(
    client: AsyncClient, captured: list[logging.LogRecord]
) -> None:
    """Probes poll this on a short interval; logging it buries everything else."""
    await client.get("/health")

    assert not _lines(captured, "request completed")


async def test_failed_request_is_logged_with_a_trace(
    app: FastAPI, client: AsyncClient, captured: list[logging.LogRecord]
) -> None:
    """The detail withheld from the client has to be in the log instead."""

    @app.get("/_test/boom")
    async def _boom() -> None:
        raise RuntimeError("the internal detail")

    await client.get("/_test/boom", headers={REQUEST_ID_HEADER: "trace-fail"})

    failed = _lines(captured, "request failed")
    assert failed
    assert failed[0].exc_info is not None
    assert getattr(failed[0], "request_id", "") == "trace-fail"


def _record(**extras: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="verdict for %s",
        args=("claim-1",),
        exc_info=None,
    )
    for key, value in extras.items():
        setattr(record, key, value)
    return record


def test_json_formatter_emits_one_object_per_line() -> None:
    line = JsonFormatter().format(_record(desk="text", confidence=0.91))

    assert "\n" not in line
    payload = json.loads(line)
    assert payload["message"] == "verdict for claim-1"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["desk"] == "text"
    assert payload["confidence"] == 0.91


def test_json_formatter_omits_an_absent_request_id() -> None:
    """A null field on every line outside a request is noise."""
    payload = json.loads(JsonFormatter().format(_record()))

    assert "request_id" not in payload


def test_json_formatter_survives_an_unserialisable_extra() -> None:
    """A bad `extra` must not turn one log call into a second exception."""

    class Opaque:
        def __repr__(self) -> str:
            return "<opaque>"

    payload = json.loads(JsonFormatter().format(_record(thing=Opaque())))

    assert payload["thing"] == "<opaque>"


def test_console_formatter_renders_extras_inline() -> None:
    record = _record(desk="image")
    record.request_id = "abc123"

    line = ConsoleFormatter().format(record)

    assert "verdict for claim-1" in line
    assert "[abc123]" in line
    assert "desk='image'" in line
    # The id is already in the brackets; repeating it in the extras is clutter.
    assert "request_id=" not in line


def test_request_id_filter_never_drops_a_record() -> None:
    """A filter that returned False would silence the line it annotates."""
    record = _record()

    assert RequestIdFilter().filter(record) is True
    assert record.request_id == ""  # type: ignore[attr-defined]
