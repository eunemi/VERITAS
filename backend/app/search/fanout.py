"""Asking every configured provider at once, and reporting what each one did.

This is where "multiple independent websites" starts being true at the index
level. One query goes to every provider that has a key, concurrently, and the
result is not a merged list — it is every provider's answer kept separate, plus a
record of what happened to each.

The design rule here is narrow and absolute: **a provider's failure must cost the
dossier that provider's results and nothing else.** So the fan-out never lets one
error cancel its siblings (:func:`asyncio.gather` with ``return_exceptions=True``,
not a task group, which would cancel the others on the first exception), never
swallows an error into an empty list, and never reports a provider as having
searched when it did not. Every provider in the roster leaves exactly one
:class:`~app.domain.research.ProviderOutcome` behind, whatever became of it.

What this module does *not* do is decide anything about the results. It does not
deduplicate, rank, cluster or score. It converts each provider's answer into
:class:`~app.domain.research.Retrieval` records — the audit trail — and stops.
That boundary is deliberate: it is what lets everything in :mod:`app.research` be
pure, synchronous and testable with nothing installed, while every module that
touches the network lives here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.core.config import SearchProvider, Settings
from app.core.errors import ConfigurationError, VeritasError
from app.core.logging import get_logger
from app.domain import ProviderOutcome, ProviderStatus, Retrieval
from app.providers.http import redact
from app.providers.outcomes import outcome
from app.search.base import SearchClient, SearchResult

__all__ = ["Harvest", "Task", "harvest"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Task:
    """One claim and the queries to run for it."""

    claim: str
    queries: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Harvest:
    """Everything the providers returned, still separated by claim.

    ``retrievals`` is aligned with the tasks it was built from — index *i* holds
    what was found for task *i* — rather than keyed by claim text, because two
    claims in one request can be identical after rewriting and collapsing them
    would silently drop one.
    """

    retrievals: tuple[tuple[Retrieval, ...], ...]
    outcomes: tuple[ProviderOutcome, ...]


async def harvest(
    tasks: Sequence[Task],
    *,
    settings: Settings,
    now: datetime,
) -> Harvest:
    """Run every task's queries against every configured provider.

    ``now`` is passed to each client so that a relative age resolves against the
    moment the dossier was assembled, identically for every provider.

    Providers with no API key are not an error: they are recorded as
    :attr:`~app.domain.research.ProviderStatus.SKIPPED` with the reason, which is
    what makes a one-provider deployment legible rather than mysterious.
    """
    clients: list[tuple[SearchProvider, SearchClient]] = []
    outcomes: list[ProviderOutcome] = []
    secrets = settings.search_secrets()

    for provider in _roster(settings):
        try:
            clients.append((provider, _open(provider, settings)))
        except ConfigurationError as exc:
            outcomes.append(
                ProviderOutcome(
                    provider=str(provider),
                    status=ProviderStatus.SKIPPED,
                    code=exc.code,
                    detail=redact(str(exc), *secrets),
                )
            )
        except VeritasError as exc:
            # An unregistered provider, or one whose constructor rejected the
            # settings. Recorded rather than raised: the other providers can still
            # answer, and a dossier from two engines beats a 500 from three.
            outcomes.append(
                ProviderOutcome(
                    provider=str(provider),
                    status=ProviderStatus.FAILED,
                    code=exc.code,
                    detail=redact(str(exc), *secrets),
                )
            )

    if not clients:
        return Harvest(
            retrievals=tuple(() for _ in tasks),
            outcomes=tuple(sorted(outcomes, key=lambda o: o.provider)),
        )

    try:
        gathered = await _run(clients, tasks, settings=settings, now=now)
    finally:
        # Close every pool even when a task raised out of the gather, so a failed
        # request cannot leak a connection into the next one.
        await asyncio.gather(
            *(client.aclose() for _, client in clients),
            return_exceptions=True,
        )

    return _assemble(
        gathered,
        tasks=tasks,
        clients=clients,
        skipped=outcomes,
        secrets=secrets,
    )


def _roster(settings: Settings) -> tuple[SearchProvider, ...]:
    """The configured providers, in order, without repeats.

    A duplicate in ``SEARCH_PROVIDERS`` — easy to introduce in an env var, since
    it is a comma-separated list — would otherwise send every query twice and
    double that provider's contribution to ``results``, making one engine look
    like two. Deduplicating here rather than validating in the settings keeps a
    typo from being a startup failure.
    """
    seen: list[SearchProvider] = []
    for provider in settings.SEARCH_PROVIDERS:
        if provider not in seen:
            seen.append(provider)
    return tuple(seen)


# --------------------------------------------------------------------- jobs ----


@dataclass(frozen=True, slots=True)
class _Job:
    """One provider, one query, one claim."""

    provider: str
    task: int
    query: str


async def _run(
    clients: list[tuple[SearchProvider, SearchClient]],
    tasks: Sequence[Task],
    *,
    settings: Settings,
    now: datetime,
) -> list[tuple[_Job, list[SearchResult] | BaseException]]:
    """Every (provider, query) pair, run concurrently, in a stable order.

    One semaphore per provider rather than one shared across all of them: the
    quotas being protected are per-key, and a shared limit would let a fast
    provider's queue delay a slow provider's first request for no reason.

    ``return_exceptions=True`` is the load-bearing argument. Without it the first
    failure cancels every other in-flight request, so one expired key would empty
    the dossier — and the outcomes would then report providers as having failed
    when they were cancelled mid-flight, which is a false statement about what was
    searched.
    """
    limits = {
        str(provider): asyncio.Semaphore(max(1, settings.SEARCH_CONCURRENCY))
        for provider, _ in clients
    }
    by_name = {str(provider): client for provider, client in clients}

    jobs = [
        _Job(provider=str(provider), task=index, query=query)
        for provider, _ in clients
        for index, task in enumerate(tasks)
        for query in task.queries
    ]

    async def one(job: _Job) -> list[SearchResult]:
        async with limits[job.provider]:
            return await by_name[job.provider].search(
                job.query,
                max_results=settings.SEARCH_MAX_RESULTS,
                now=now,
            )

    settled = await asyncio.gather(
        *(one(job) for job in jobs), return_exceptions=True
    )
    return list(zip(jobs, settled, strict=True))


def _assemble(
    gathered: list[tuple[_Job, list[SearchResult] | BaseException]],
    *,
    tasks: Sequence[Task],
    clients: list[tuple[SearchProvider, SearchClient]],
    skipped: list[ProviderOutcome],
    secrets: tuple[str, ...],
) -> Harvest:
    """Turn settled jobs into retrievals per task and one outcome per provider."""
    retrievals: list[list[Retrieval]] = [[] for _ in tasks]
    ran: dict[str, int] = {}
    failed: dict[str, int] = {}
    counts: dict[str, int] = {}
    queries: dict[str, list[str]] = {}
    errors: dict[str, BaseException] = {}

    for provider, _ in clients:
        name = str(provider)
        ran[name] = failed[name] = counts[name] = 0
        queries[name] = []

    for job, outcome in gathered:
        queries[job.provider].append(job.query)
        if isinstance(outcome, BaseException):
            failed[job.provider] += 1
            errors.setdefault(job.provider, outcome)
            logger.warning(
                "search query failed",
                extra={
                    "provider": job.provider,
                    "error": type(outcome).__name__,
                    "detail": redact(str(outcome), *secrets),
                },
            )
            continue
        ran[job.provider] += 1
        counts[job.provider] += len(outcome)
        retrievals[job.task].extend(
            _retrieval(job, result, rank)
            for rank, result in enumerate(outcome, start=1)
        )

    outcomes = list(skipped)
    for provider, _ in clients:
        name = str(provider)
        outcomes.append(
            _outcome(
                name,
                ran=ran[name],
                failed=failed[name],
                results=counts[name],
                queries=tuple(queries[name]),
                error=errors.get(name),
                secrets=secrets,
            )
        )
    outcomes.sort(key=lambda o: o.provider)

    return Harvest(
        retrievals=tuple(tuple(found) for found in retrievals),
        outcomes=tuple(outcomes),
    )


def _outcome(
    provider: str,
    *,
    ran: int,
    failed: int,
    results: int,
    queries: tuple[str, ...],
    error: BaseException | None,
    secrets: tuple[str, ...],
) -> ProviderOutcome:
    """This provider's outcome, with ``search_error`` as the fallback code.

    A thin wrapper over :func:`app.providers.outcomes.outcome`, which is shared with
    :mod:`app.factcheck.lookup` — the three-way SEARCHED / PARTIAL / FAILED split is
    documented there. All this adds is which error code an exception that is not a
    :class:`~app.core.errors.VeritasError` should be reported under.
    """
    return outcome(
        provider,
        ran=ran,
        failed=failed,
        results=results,
        queries=queries,
        error=error,
        secrets=secrets,
        code="search_error",
    )


def _retrieval(job: _Job, result: SearchResult, rank: int) -> Retrieval:
    """One provider's result, recorded as the audit trail entry for it.

    A straight copy. Every field is what the provider sent, and the three the
    provider did not send — rank, query, provider name — are facts about the
    request rather than about the page.
    """
    return Retrieval(
        provider=job.provider,
        query=job.query,
        rank=rank,
        url=result.url,
        title=result.title,
        snippet=result.snippet,
        score=result.score,
        published_at=result.published_at,
        date_basis=result.date_basis,
        date_text=result.date_text,
    )


def _open(provider: SearchProvider, settings: Settings) -> SearchClient:
    """Build one client, or raise the reason it cannot be built.

    Resolution goes through the registry rather than importing a client directly,
    so a test can substitute a fake provider and this module needs no knowledge of
    which vendors exist.

    The import is inside the function because :mod:`app.search` imports the
    provider modules in order to register them, and this module is imported from
    there — a module-level import would be a cycle. Deferring it also means
    :func:`harvest` can be imported and its pure helpers tested without pulling in
    every client, and therefore without ``httpx``.
    """
    from app.search import search_clients

    return search_clients.resolve(provider, settings)
