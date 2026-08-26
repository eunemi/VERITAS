"""The error envelope.

Every failure this API can produce has to come back as ``{"error": {...}}`` with a
stable ``code`` and, above all, the request id — that id is the only thread tying
a response a user is looking at to the stack trace in the logs.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import BaseModel

from app.core.errors import NotFoundError, ProviderTimeoutError
from app.core.middleware import REQUEST_ID_HEADER

ENVELOPE_KEYS = {"code", "message", "details", "request_id"}


async def test_application_error_renders_the_envelope(
    app: FastAPI, client: AsyncClient
) -> None:
    @app.get("/_test/missing")
    async def _missing() -> None:
        raise NotFoundError("No such investigation.", details={"id": "abc"})

    response = await client.get("/_test/missing")

    assert response.status_code == 404
    error = response.json()["error"]
    assert set(error) == ENVELOPE_KEYS
    assert error["code"] == "not_found"
    assert error["message"] == "No such investigation."
    assert error["details"] == {"id": "abc"}


async def test_provider_error_reports_which_provider(
    app: FastAPI, client: AsyncClient
) -> None:
    """``provider`` reaches the body without the caller building the dict."""

    @app.get("/_test/slow")
    async def _slow() -> None:
        raise ProviderTimeoutError("Upstream took too long.", provider="tavily")

    response = await client.get("/_test/slow")

    assert response.status_code == 504
    error = response.json()["error"]
    assert error["code"] == "provider_timeout"
    assert error["details"]["provider"] == "tavily"


async def test_error_body_request_id_matches_the_header(
    app: FastAPI, client: AsyncClient
) -> None:
    """The id in the body is what a user reports; it must be the real one."""

    @app.get("/_test/missing")
    async def _missing() -> None:
        raise NotFoundError()

    response = await client.get(
        "/_test/missing", headers={REQUEST_ID_HEADER: "trace-known"}
    )

    assert response.json()["error"]["request_id"] == "trace-known"
    assert response.headers[REQUEST_ID_HEADER] == "trace-known"


async def test_unexpected_error_still_carries_a_request_id(
    app: FastAPI, client: AsyncClient
) -> None:
    """Regression: the catch-all runs outside RequestContextMiddleware.

    Starlette's ``ServerErrorMiddleware`` sits above our middleware, so by the
    time a 500 is rendered the request-id context variable has been unbound. If
    the handler reads only the context variable, this body comes back with
    ``request_id: null`` — which is exactly the response where the id matters
    most, because it is the only way to find the logged trace.
    """

    @app.get("/_test/boom")
    async def _boom() -> None:
        raise RuntimeError("the internal detail")

    response = await client.get("/_test/boom", headers={REQUEST_ID_HEADER: "trace-500"})

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["request_id"] == "trace-500"


async def test_unexpected_error_leaks_nothing(
    app: FastAPI, client: AsyncClient
) -> None:
    """The trace goes to the log; the client gets a generic message."""

    @app.get("/_test/boom")
    async def _boom() -> None:
        raise RuntimeError("connection string postgres://user:hunter2@db")

    response = await client.get("/_test/boom")

    body = response.text
    assert response.json()["error"]["code"] == "internal_error"
    assert "hunter2" not in body
    assert "RuntimeError" not in body
    assert "Traceback" not in body


async def test_unknown_path_uses_the_envelope(client: AsyncClient) -> None:
    """Framework-raised 404s go through the same shape as our own."""
    response = await client.get("/_test/nothing-here")

    assert response.status_code == 404
    error = response.json()["error"]
    assert set(error) == ENVELOPE_KEYS
    assert error["code"] == "not_found"


async def test_method_not_allowed_uses_the_envelope(client: AsyncClient) -> None:
    response = await client.post("/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


async def test_request_validation_names_the_bad_field(
    app: FastAPI, client: AsyncClient
) -> None:
    class Submission(BaseModel):
        claim: str

    @app.post("/_test/submit")
    async def _submit(payload: Submission) -> dict[str, str]:
        return {"claim": payload.claim}

    response = await client.post("/_test/submit", json={})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    fields = [item["field"] for item in error["details"]["errors"]]
    assert "body.claim" in fields


async def test_validation_details_are_serialisable(
    app: FastAPI, client: AsyncClient
) -> None:
    """Pydantic's raw ``ctx`` can hold objects that will not serialise.

    Rendering the response is the last thing that happens on a failed request; if
    it raises, the client gets nothing at all.
    """

    class Submission(BaseModel):
        weight: float

    @app.post("/_test/weigh")
    async def _weigh(payload: Submission) -> dict[str, float]:
        return {"weight": payload.weight}

    response = await client.post("/_test/weigh", json={"weight": "not-a-number"})

    assert response.status_code == 422
    for item in response.json()["error"]["details"]["errors"]:
        assert set(item) == {"field", "message", "type"}
        assert all(isinstance(value, str) for value in item.values())
