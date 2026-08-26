"""The health endpoint and the request-id middleware that wraps it."""

from __future__ import annotations

from datetime import datetime

import pytest
from httpx import AsyncClient

from app.core.config import Settings
from app.core.middleware import REQUEST_ID_HEADER, RequestContextMiddleware

# Both mounts are the same route object; the point of testing both is that the
# factory actually included it twice, at the paths documented in the route module.
HEALTH_PATHS = ["/health", "/api/v1/health"]


@pytest.mark.parametrize("path", HEALTH_PATHS)
async def test_health_reports_the_running_service(
    client: AsyncClient, settings: Settings, path: str
) -> None:
    response = await client.get(path)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == settings.APP_NAME
    assert body["version"] == settings.APP_VERSION
    assert body["environment"] == settings.ENVIRONMENT.value


@pytest.mark.parametrize("path", HEALTH_PATHS)
async def test_health_timestamp_is_timezone_aware(
    client: AsyncClient, path: str
) -> None:
    """A naive timestamp is unusable to a client in another zone."""
    body = (await client.get(path)).json()

    moment = datetime.fromisoformat(body["timestamp"])
    assert moment.tzinfo is not None
    assert moment.utcoffset() is not None


async def test_health_is_not_versioned_away(client: AsyncClient) -> None:
    """Both mounts answer identically apart from the timestamp."""
    unversioned = (await client.get("/health")).json()
    versioned = (await client.get("/api/v1/health")).json()

    assert {k: v for k, v in unversioned.items() if k != "timestamp"} == {
        k: v for k, v in versioned.items() if k != "timestamp"
    }


async def test_response_carries_a_request_id(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.headers.get(REQUEST_ID_HEADER)


async def test_supplied_request_id_is_honoured(client: AsyncClient) -> None:
    """A trace started at the frontend stays one trace."""
    response = await client.get("/health", headers={REQUEST_ID_HEADER: "trace-abc-123"})

    assert response.headers[REQUEST_ID_HEADER] == "trace-abc-123"


async def test_oversized_request_id_is_truncated(client: AsyncClient) -> None:
    """The header is attacker-controlled and lands in every log line."""
    limit = RequestContextMiddleware.MAX_INBOUND_LENGTH
    response = await client.get("/health", headers={REQUEST_ID_HEADER: "x" * 5_000})

    assert response.headers[REQUEST_ID_HEADER] == "x" * limit


async def test_blank_request_id_is_replaced(client: AsyncClient) -> None:
    """An empty header must not produce an empty correlation id."""
    response = await client.get("/health", headers={REQUEST_ID_HEADER: "   "})

    assert response.headers[REQUEST_ID_HEADER].strip()


async def test_each_request_gets_a_distinct_id(client: AsyncClient) -> None:
    first = (await client.get("/health")).headers[REQUEST_ID_HEADER]
    second = (await client.get("/health")).headers[REQUEST_ID_HEADER]

    assert first != second


async def test_docs_are_open_outside_production(client: AsyncClient) -> None:
    assert (await client.get("/openapi.json")).status_code == 200
