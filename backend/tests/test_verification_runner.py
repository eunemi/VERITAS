"""Admission and concurrency limits for background examinations."""

from __future__ import annotations

import asyncio

import pytest

from app.core.errors import ServiceBusyError
from app.services.verification import VerificationRunner


class _SlowService:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self, verification_id: str) -> None:
        self.started.set()
        await self.release.wait()


@pytest.mark.asyncio
async def test_runner_rejects_jobs_beyond_active_and_queued_capacity() -> None:
    runner = VerificationRunner(max_concurrent=1, max_queued=1)
    first = _SlowService()
    second = _SlowService()

    await runner.reserve()
    first_task = asyncio.create_task(runner.run(first, "first"))
    await first.started.wait()

    await runner.reserve()
    second_task = asyncio.create_task(runner.run(second, "second"))

    with pytest.raises(ServiceBusyError):
        await runner.reserve()

    first.release.set()
    await first_task
    second.release.set()
    await second_task


@pytest.mark.asyncio
async def test_runner_releases_capacity_when_a_job_raises() -> None:
    runner = VerificationRunner(max_concurrent=1, max_queued=0)

    class Broken:
        async def run(self, verification_id: str) -> None:
            raise RuntimeError("test failure")

    await runner.reserve()
    with pytest.raises(RuntimeError):
        await runner.run(Broken(), "broken")

    await runner.reserve()
    await runner.release()


@pytest.mark.asyncio
async def test_runner_releases_capacity_when_waiting_job_is_cancelled() -> None:
    runner = VerificationRunner(max_concurrent=1, max_queued=1)
    first = _SlowService()
    second = _SlowService()

    await runner.reserve()
    first_task = asyncio.create_task(runner.run(first, "first"))
    await first.started.wait()

    await runner.reserve()
    second_task = asyncio.create_task(runner.run(second, "second"))
    await asyncio.sleep(0)
    second_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await second_task

    first.release.set()
    await first_task
    await runner.reserve()
    await runner.release()


@pytest.mark.asyncio
async def test_runner_recovers_open_jobs_within_its_capacity() -> None:
    runner = VerificationRunner(max_concurrent=1, max_queued=1)

    class Repository:
        async def list_open_ids(self, *, limit: int = 100) -> tuple[str, ...]:
            assert limit == 2
            return ("old-1", "old-2", "old-3")

    class Service:
        def __init__(self) -> None:
            self.seen: list[str] = []
            self.finished = asyncio.Event()

        async def run(self, verification_id: str) -> None:
            self.seen.append(verification_id)
            if len(self.seen) == 2:
                self.finished.set()

    service = Service()
    runner.start_recovery(service, Repository(), storage_timeout=1)

    await asyncio.wait_for(service.finished.wait(), timeout=1)
    await runner.shutdown()

    assert service.seen == ["old-1", "old-2"]
