"""The contract every fact-check database implements.

Narrow, like :mod:`app.search.base`, and for the same reason: a client's whole job is
to turn a query into records and to be honest about what it did not get. The judgements
— what a rating means, whether the database's claim is the caller's claim — happen above
it in :mod:`app.research.reviews`, and none of them belongs in a client.

One rule is stricter here than anywhere else in the codebase. **A client must not
interpret a rating.** :attr:`~app.domain.factcheck.Review.rating` arrives as the
publisher spelled it, and :attr:`~app.domain.factcheck.Review.stance` is left at its
default for :func:`app.research.reviews.select` to fill. A client that mapped ``"Four
Pinocchios"`` onto a scale would be making an editorial judgement inside an HTTP
wrapper, where it could not be reviewed as one and where nothing could see it happen.

The types the seam speaks live in :mod:`app.domain.factcheck` rather than here. There is
no narrower vendor-shaped intermediate the way :class:`~app.search.base.SearchResult` is
narrower than :class:`~app.domain.research.Retrieval`: a fact check needs nothing added
about the request that made it appear, so a second type would be a copy.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from app.domain import ReviewedClaim


@runtime_checkable
class FactCheckClient(Protocol):
    """Looks up fact checks other organisations have already published.

    Implementations raise :class:`app.core.errors.FactCheckError` on failure. They do
    not return an empty list to signal a problem: **"nobody has reviewed this claim"
    and "the lookup did not happen" are opposite answers**, and the first is the more
    dangerous one to get wrong, because the natural reading of it is that the claim is
    unexamined. :class:`~app.domain.research.ProviderOutcome` can only tell them apart
    if the second raises.
    """

    name: str

    async def lookup(
        self,
        query: str,
        *,
        max_results: int = 10,
        language: str = "",
        max_age_days: int = 0,
        now: datetime,
    ) -> list[ReviewedClaim]:
        """Return the database's records for ``query``, most relevant first.

        Claim-major: one entry per claim the database holds, carrying every review
        published on it. Two organisations reviewing the same claim is one record with
        two reviews, not two records.

        ``max_results`` is a ceiling, not a target, and the ordering is the database's
        own relevance ranking — which is why a caller must not read the length of this
        list as a measure of how contested a claim is.

        ``language`` is a BCP-47 tag and ``max_age_days`` a window, both passed through
        when non-empty and both filters on the *request*: a database is free to return
        a record outside them, so neither may be relied on downstream.

        ``now`` is the instant dates resolve against, required rather than read from
        the clock inside the client, for the reason given on
        :meth:`app.search.base.SearchClient.search` — one dossier, one reference point,
        and a recorded response that parses the same way every time.
        """
        ...

    async def aclose(self) -> None:
        """Release the underlying connection pool."""
        ...
