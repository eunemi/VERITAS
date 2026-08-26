"""Asking the fact-check database about every claim at once, and reporting what it did.

The analogue of :mod:`app.search.fanout`, and it inherits that module's one absolute
rule: **a failure must cost the dossier that provider's results and nothing else.** So
this never lets one claim's error cancel the others (:func:`asyncio.gather` with
``return_exceptions=True``, not a task group), never swallows an error into an empty
list, and never reports the provider as having looked when it did not.

The rule is sharper here than it is for search, because of what an empty answer means. A
search that returns nothing says the web is quiet on a claim. A fact-check lookup that
returns nothing says *no fact-checker has ruled on this claim* — a statement about the
world whose natural reading is that the claim is unexamined, and a very inviting thing
for a reader to treat as licence. If a spent quota or an expired key could produce that
answer, the service would be making that statement on the strength of a billing problem.
Hence :class:`~app.domain.research.ProviderStatus`: ``SEARCHED`` with zero records is a
finding, ``FAILED`` is an admission, and they are never the same value.

Where the shape differs from search: one query per claim, not several. The queries in
:mod:`app.research.queries` are built to surface *documents*, with keywords stripped and
recombined to widen recall — the wrong instrument entirely for an index keyed on claim
wording, where the claim as stated is the best possible query and a reworded variant
would match a different record. So the claim text goes in unmodified, and what the
database thought it matched comes back in
:attr:`~app.domain.factcheck.ReviewedClaim.text` for :mod:`app.research.reviews` to
judge.

Like the fan-out, this decides nothing. It returns the database's records untouched and
one :class:`~app.domain.research.ProviderOutcome`, and stops.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.core.config import Settings
from app.core.errors import ConfigurationError, VeritasError
from app.core.logging import get_logger
from app.domain import ProviderOutcome, ProviderStatus, ReviewedClaim
from app.factcheck.base import FactCheckClient
from app.providers.http import redact
from app.providers.outcomes import outcome

__all__ = ["Checked", "check"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Checked:
    """Everything the database returned, still separated by claim.

    ``found`` is aligned with the claims it was built from — index *i* holds what came
    back for claim *i* — rather than keyed by claim text, because two claims in one
    request can be identical after extraction and collapsing them would silently drop
    one.

    ``outcomes`` is a tuple for one provider so that the shape matches
    :attr:`app.domain.research.Dossier.providers` and a second fact-check database
    could be added without changing anything downstream.
    """

    found: tuple[tuple[ReviewedClaim, ...], ...]
    outcomes: tuple[ProviderOutcome, ...]


async def check(
    claims: Sequence[str],
    *,
    settings: Settings,
    now: datetime,
) -> Checked:
    """Look up every claim in ``claims`` against the configured database.

    ``now`` is passed to the client so that every date in one dossier resolves against
    the moment it was assembled.

    A database with no API key is not an error: it is recorded as
    :attr:`~app.domain.research.ProviderStatus.SKIPPED` with the reason, which is what
    makes a deployment without a fact-check key legible rather than mysterious. That is
    the common case — the key is free but separate from the search keys — so the path
    is a first-class outcome rather than an edge.
    """
    secrets = settings.fact_check_secrets()
    provider = str(settings.FACT_CHECK_PROVIDER)
    empty = tuple(() for _ in claims)

    try:
        client = _open(settings)
    except ConfigurationError as exc:
        return Checked(
            found=empty,
            outcomes=(
                ProviderOutcome(
                    provider=provider,
                    status=ProviderStatus.SKIPPED,
                    code=exc.code,
                    detail=redact(str(exc), *secrets),
                ),
            ),
        )
    except VeritasError as exc:
        # An unregistered provider, or one whose constructor rejected the settings.
        # Recorded rather than raised: the dossier's web research is unaffected, and a
        # dossier without fact checks beats a 500 with neither.
        return Checked(
            found=empty,
            outcomes=(
                ProviderOutcome(
                    provider=provider,
                    status=ProviderStatus.FAILED,
                    code=exc.code,
                    detail=redact(str(exc), *secrets),
                ),
            ),
        )

    if not claims:
        # No request was made, and saying SEARCHED would be a claim about an index
        # nobody asked anything of. Closed anyway: `_open` may have built a pool.
        await client.aclose()
        return Checked(
            found=(),
            outcomes=(
                ProviderOutcome(
                    provider=provider,
                    status=ProviderStatus.SKIPPED,
                    code="no_claims",
                    detail="no claims to look up",
                ),
            ),
        )

    try:
        settled = await _run(client, claims, settings=settings, now=now)
    finally:
        # Closed even when a lookup raised out of the gather, so a failed request
        # cannot leak a connection into the next one.
        await client.aclose()

    return _assemble(settled, claims=claims, provider=provider, secrets=secrets)


async def _run(
    client: FactCheckClient,
    claims: Sequence[str],
    *,
    settings: Settings,
    now: datetime,
) -> list[list[ReviewedClaim] | BaseException]:
    """One lookup per claim, concurrently, in claim order.

    ``return_exceptions=True`` is the load-bearing argument, for the same reason it is
    in :func:`app.search.fanout._run`: without it the first failure cancels every other
    in-flight lookup, so one rate-limited claim would empty the whole fact-check
    section — and the outcome would then report the provider as having failed on claims
    it was cancelled out of, which is a false statement about what was looked up.

    The semaphore is per-call rather than per-process because the quota being protected
    is per-key and the API's is a shared daily budget. Two is the default: enough to
    overlap the round trips, low enough that a ten-claim request does not arrive as a
    burst.
    """
    limit = asyncio.Semaphore(max(1, settings.FACT_CHECK_CONCURRENCY))

    async def one(claim: str) -> list[ReviewedClaim]:
        async with limit:
            return await client.lookup(
                claim,
                max_results=settings.FACT_CHECK_MAX_RESULTS,
                language=settings.FACT_CHECK_LANGUAGE,
                max_age_days=settings.FACT_CHECK_MAX_AGE_DAYS,
                now=now,
            )

    settled = await asyncio.gather(
        *(one(claim) for claim in claims), return_exceptions=True
    )
    return list(settled)


def _assemble(
    settled: Sequence[list[ReviewedClaim] | BaseException],
    *,
    claims: Sequence[str],
    provider: str,
    secrets: tuple[str, ...],
) -> Checked:
    """Turn settled lookups into records per claim and one outcome for the provider."""
    found: list[tuple[ReviewedClaim, ...]] = []
    ran = failed = results = 0
    first: BaseException | None = None

    for claim, result in zip(claims, settled, strict=True):
        if isinstance(result, BaseException):
            failed += 1
            if first is None:
                first = result
            logger.warning(
                "fact check lookup failed",
                extra={
                    "provider": provider,
                    "error": type(result).__name__,
                    "detail": redact(str(result), *secrets),
                },
            )
            # An empty tuple for a claim that *failed*, which on its own would be
            # indistinguishable from a claim nobody has reviewed. The outcome is what
            # distinguishes them, and it is why this function cannot just return
            # `found`.
            found.append(())
            continue
        ran += 1
        results += len(result)
        found.append(tuple(result))
        logger.debug(
            "fact check lookup complete",
            extra={"provider": provider, "claim": claim, "records": len(result)},
        )

    return Checked(
        found=tuple(found),
        outcomes=(
            outcome(
                provider,
                ran=ran,
                failed=failed,
                results=results,
                queries=tuple(claims),
                error=first,
                secrets=secrets,
                code="fact_check_error",
            ),
        ),
    )


def _open(settings: Settings) -> FactCheckClient:
    """Build the client, or raise the reason it cannot be built.

    Resolution goes through the registry rather than importing the client directly, so
    a test can substitute a fake database and this module needs no knowledge of which
    ones exist.

    The import is inside the function because :mod:`app.factcheck` imports the client
    modules in order to register them, and this module is imported from there — a
    module-level import would be a cycle. Deferring it also means :func:`check` can be
    imported and its pure helpers tested without ``httpx``.
    """
    from app.factcheck import get_fact_check_client

    return get_fact_check_client(settings)
