"""Assembling one claim's retrievals into the dossier a desk will read.

Everything above this module produces parts: :mod:`app.search` returns what three
engines said, :mod:`app.research.dedupe` decides what counts as one page and one
story, :mod:`app.research.evidence` decides which sentence of a snippet bears on the
claim. This is where they become a :class:`~app.domain.research.ClaimResearch`.

Two decisions here are the ones a reader would want explained.

**A date is chosen, never composed.** Three providers report publication dates in
three different senses and a fourth is readable from the URL, so the strongest basis
available wins and :attr:`~app.domain.research.Source.date_basis` says which it was.
Every provider's own answer stays on its :class:`~app.domain.research.Retrieval`, so a
disagreement between two engines is visible in the dossier rather than resolved into a
single confident-looking timestamp. Nothing here averages dates, and nothing prefers
the earliest or the latest: both would be this service inventing a date that no
provider stated.

**Ordering does not manufacture diversity.** Sources come out strongest-first, by how
well their evidence matches the claim, and eight mastheads carrying one wire report
will fill the top eight places if that is what was found. It is tempting to interleave
publishers so the list *looks* independent — and that would misrepresent strength to
flatter a number. The honest instrument is already in place: those eight share a
:attr:`~app.domain.research.Source.cluster`, so
:attr:`~app.domain.research.ClaimResearch.stories` reports one story beside eight
domains, and a reader sees the concentration instead of an ordering that hides it.

There is also no cap on sources here, deliberately. How much is searched is decided by
the fan-out — providers times queries times results per query, all configured — and a
second limit at this layer would discard evidence that was actually retrieved, at the
point furthest from anyone who could report the loss. If a response needs to be
smaller, that belongs where the truncation can be stated.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from app.domain.claims import ExtractedClaim
from app.domain.factcheck import FactCheck
from app.domain.research import ClaimResearch, DateBasis, Retrieval, Source
from app.research import dedupe, urls
from app.research import evidence as evidence_

__all__ = ["BASIS_STRENGTH", "for_claim"]

#: How far each basis is trusted, strongest first. The order is
#: :class:`~app.domain.research.DateBasis`'s own, made comparable.
#:
#: A stated publication date beats one the provider would not commit to publication or
#: modification, which beats a relative age that only means anything against the
#: moment of retrieval, which beats a date this service read out of a URL path. The
#: gaps are real: only the first is quotable as "published on".
BASIS_STRENGTH: dict[DateBasis, int] = {
    DateBasis.PROVIDER: 0,
    DateBasis.PROVIDER_MODIFIED: 1,
    DateBasis.PROVIDER_RELATIVE: 2,
    DateBasis.URL_PATH: 3,
}


def for_claim(
    claim: ExtractedClaim,
    *,
    queries: Sequence[str],
    retrievals: Sequence[Retrieval],
    now: datetime,
    fact_checks: Sequence[FactCheck] = (),
    evidence_limit: int = evidence_.MAX_EVIDENCE,
) -> ClaimResearch:
    """Everything found for ``claim``, deduplicated, dated, quoted and ordered.

    ``queries`` is recorded verbatim as
    :attr:`~app.domain.research.ClaimResearch.queries` and is **not** rebuilt here.
    The caller sent those strings to the providers; regenerating them would produce a
    plausible list rather than a true one, and the first time query construction
    changed under a cached result the record would quietly stop matching what was
    searched.

    ``retrievals`` is what the fan-out found for this claim and this claim only.
    Passing another claim's retrievals in would let unrelated coverage be clustered as
    the same story and counted as corroboration.

    ``fact_checks`` is carried through untouched, already scored and ordered by
    :func:`app.research.reviews.select`. It is a parameter rather than something this
    module assembles because a published fact check is not a search result: it did not
    come from a provider in ``retrievals``, it must not be deduplicated against the web
    pages, and it must not be ranked among them. Passing it here rather than attaching
    it afterwards keeps a :class:`~app.domain.research.ClaimResearch` something that is
    only ever constructed complete.

    ``now`` anchors any date read from a URL path. It is the dossier's
    :attr:`~app.domain.research.Dossier.retrieved_at`, not a fresh clock reading, so
    two sources in one dossier are dated against the same instant.

    An empty result is returned for a claim nothing was found for. That is not a
    finding on its own — :attr:`~app.domain.research.Dossier.searched` is what
    separates "nothing is out there" from "nothing was asked", and it lives on the
    dossier because it is a fact about the providers rather than about the claim.
    """
    needle = evidence_.Needle.of(claim)
    grouping = dedupe.group(retrievals)

    built = [
        _source(page, needle=needle, now=now, limit=evidence_limit)
        for page in grouping.pages
    ]
    built.sort(key=_strength)

    numbered = tuple(
        replace(source, ref=index) for index, source in enumerate(built, start=1)
    )

    # Clustered last, on the final order, because the cluster ids are numbered by
    # each cluster's representative and would otherwise be assigned against an
    # ordering the response does not show.
    return ClaimResearch(
        claim=claim.text,
        queries=tuple(queries),
        sources=dedupe.cluster(numbered),
        fact_checks=tuple(fact_checks),
    )


def _source(
    page: dedupe.PageGroup,
    *,
    needle: evidence_.Needle,
    now: datetime,
    limit: int,
) -> Source:
    """One :class:`~app.domain.research.Source` from one page's retrievals.

    ``ref`` is 1 here and replaced once the sources are ordered: a reference number
    that changed meaning between construction and output would be worse than none.
    """
    dated = _dated(page, now=now)
    return Source(
        ref=1,
        url=page.url,
        urls=page.urls,
        title=page.title,
        domain=page.domain,
        host=page.host,
        evidence=evidence_.select(needle, page.retrievals, limit=limit),
        retrievals=page.retrievals,
        published_at=dated[0],
        date_basis=dated[1],
        date_text=dated[2],
    )


def _dated(
    page: dedupe.PageGroup, *, now: datetime
) -> tuple[datetime | None, DateBasis | None, str | None]:
    """This page's date, its basis, and the provider's own string for it.

    Ties within one basis go to the earlier retrieval, which is the stronger provider
    for this query — the fan-out emits them in roster order and rank order, so the
    tie-break is the ordering already established rather than a new preference
    invented here. It is a genuine coin-flip between two providers stating different
    dates with equal authority; both remain on
    :attr:`~app.domain.research.Source.retrievals` for a reader who needs to see the
    disagreement.
    """
    stated = [
        retrieval
        for retrieval in page.retrievals
        if retrieval.published_at is not None and retrieval.date_basis is not None
    ]
    if stated:
        best = min(
            enumerate(stated),
            key=lambda pair: (BASIS_STRENGTH[pair[1].date_basis], pair[0]),  # type: ignore[index]
        )[1]
        return best.published_at, best.date_basis, best.date_text

    # Nothing stated a date. Serper is like this by design, and Tavily unless the
    # request was for news, so this path is the common one rather than an edge case.
    from_path = urls.date_from_path(page.url, now=now)
    if from_path is None:
        return None, None, None
    # ``date_text`` stays unset on purpose: it is the field a reader checks a parse
    # against, and there is no provider string to check this against. Putting the URL
    # fragment there would present this service's own inference as something an
    # engine reported.
    return from_path, DateBasis.URL_PATH, None


def _strength(source: Source) -> tuple[float, int, int, str]:
    """The ordering key: how much this source has to say about *this* claim.

    Best evidence score first, then how many engines found the page, then the
    strongest rank any of them gave it, then the URL so the order is total and the
    same input always yields the same dossier.

    A source with no qualifying passage sorts last, below every scored one, and is
    still present: that a page three engines returned for this claim contains nothing
    matching it is information, and dropping it would replace that with silence.

    Recency is deliberately not part of this. A claim about 2019 is best served by a
    source from 2019, and there is no general rule that says otherwise — so dates are
    reported and not ranked on. Nor is the publisher's reputation, which belongs to
    the fact-check desk's :class:`~app.domain.enums.Reliability` judgement and would,
    applied here, silently decide which sources a desk ever sees.
    """
    best = -source.evidence[0].score if source.evidence else 1.0
    return best, -len(source.providers), source.best_rank, source.url
