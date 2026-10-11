"""The health endpoint and the request-id middleware that wraps it."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.config import Settings
from app.core.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from app.services.verification import VerificationRunner

# Both mounts are the same route object; the point of testing both is that the
# factory actually included it twice, at the paths documented in the route module.
HEALTH_PATHS = ["/health", "/api/v1/health"]
PUBLIC_HEALTH_PATH = "/api/health"


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


async def test_public_health_is_minimal_and_does_not_require_auth(
    client: AsyncClient,
) -> None:
    """The uptime-monitor contract is public and contains no deployment metadata."""
    response = await client.get(PUBLIC_HEALTH_PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "running"
    assert set(body) == {"status", "service", "timestamp"}
    moment = datetime.fromisoformat(body["timestamp"])
    assert moment.tzinfo is not None
    assert moment.utcoffset() is not None


async def test_health_handles_concurrent_probe_requests(client: AsyncClient) -> None:
    started = time.perf_counter()
    responses = await asyncio.gather(
        *(client.get(PUBLIC_HEALTH_PATH) for _ in range(25))
    )

    assert all(response.status_code == 200 for response in responses)
    assert time.perf_counter() - started < 1.0


async def test_health_stays_responsive_during_a_running_verification(
    app: FastAPI, client: AsyncClient
) -> None:
    class SlowWork:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def run(self, verification_id: str) -> None:
            self.started.set()
            await self.release.wait()

    runner = VerificationRunner(max_concurrent=1, max_queued=0)
    work = SlowWork()
    app.state.verification_runner = runner
    await runner.reserve()
    task = asyncio.create_task(runner.run(work, "health-concurrency"))
    await work.started.wait()

    try:
        responses = await asyncio.gather(
            *(client.get(PUBLIC_HEALTH_PATH) for _ in range(25))
        )
        assert all(response.status_code == 200 for response in responses)
    finally:
        work.release.set()
        await task


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


async def test_declared_oversized_body_is_rejected_before_parsing(
    client: AsyncClient, settings: Settings
) -> None:
    response = await client.post(
        "/api/v1/verify",
        content=b"{}",
        headers={"content-length": str(settings.MAX_UPLOAD_BYTES + 1)},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
    assert response.headers[REQUEST_ID_HEADER]


async def test_docs_are_open_outside_production(client: AsyncClient) -> None:
    assert (await client.get("/openapi.json")).status_code == 200
