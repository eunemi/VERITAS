"""One provider's outcome, from how many of its requests survived.

Shared by :mod:`app.search.fanout` and :mod:`app.factcheck.lookup` because the three-way
split below is not search-specific and not fact-check-specific — it is what "be honest
about a partial answer" means for any provider fanned out over several requests. Keeping
one copy is what stops the two from drifting into reporting a half-failed provider
differently.

It lives in :mod:`app.providers` rather than in one of them for the reason the package
exists: a fact-check lookup importing :mod:`app.search` to borrow a helper would be a
dependency edge between two provider families that have nothing to do with each other,
and the edge would be permanent.
"""

from __future__ import annotations

from app.core.errors import VeritasError
from app.domain import ProviderOutcome, ProviderStatus
from app.providers.http import redact

__all__ = ["outcome"]


def outcome(
    provider: str,
    *,
    ran: int,
    failed: int,
    results: int,
    queries: tuple[str, ...],
    error: BaseException | None,
    secrets: tuple[str, ...] = (),
    code: str = "provider_error",
) -> ProviderOutcome:
    """Summarise one provider's requests as a single reportable outcome.

    The three-way split is the point. All requests answered is
    :attr:`~app.domain.research.ProviderStatus.SEARCHED`, **even with zero results** —
    an index that returned nothing is a finding, and a provider that could not be
    reached is not. None answered is
    :attr:`~app.domain.research.ProviderStatus.FAILED`, carrying the first error's code
    so a client can branch on it. Some answered is
    :attr:`~app.domain.research.ProviderStatus.PARTIAL`: the results are kept *and* the
    shortfall is stated, because a rate limit that cut a batch in half has made the
    answer thinner in a way no reader could otherwise detect.

    ``code`` is the fallback for an exception that is not a
    :class:`~app.core.errors.VeritasError` — ``"search_error"`` from a search fan-out,
    ``"fact_check_error"`` from a lookup — so that a stray :class:`RuntimeError` still
    arrives labelled as the kind of thing that went wrong.

    Every message is filtered through :func:`app.providers.http.redact` against the
    configured keys before it goes anywhere. The clients already redact their own
    messages; this covers the exceptions that did not come from a client.
    """
    detail = ""
    reported = ""
    if error is not None:
        reported = error.code if isinstance(error, VeritasError) else code
        detail = redact(str(error), *secrets) or type(error).__name__

    if failed and not ran:
        return ProviderOutcome(
            provider=provider,
            status=ProviderStatus.FAILED,
            queries=queries,
            code=reported,
            detail=detail,
        )
    if failed:
        return ProviderOutcome(
            provider=provider,
            status=ProviderStatus.PARTIAL,
            queries=queries,
            results=results,
            code=reported,
            detail=f"{failed} of {failed + ran} queries failed; first error: {detail}",
        )
    return ProviderOutcome(
        provider=provider,
        status=ProviderStatus.SEARCHED,
        queries=queries,
        results=results,
    )
