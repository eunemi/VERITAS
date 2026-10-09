"""The web research service: claims in, dossier out.

This is the one place the two halves of the design meet. :mod:`app.search` owns the
network — three provider clients, a fan-out that isolates their failures from each
other — and :mod:`app.research` owns the judgement, pure and synchronous, importing
neither the network nor a language model. Neither imports the other. This service is
the seam, and it is deliberately thin: build the queries, run the fan-out, assemble
the dossier.

The seam is where :class:`app.search.fanout.Task` gets built, and that is the reason
:func:`app.research.queries.build` returns bare strings rather than tasks. ``Task``
lives on the network side; a research module that constructed one would have to import
:mod:`app.search`, and the import rule that keeps the research package testable with
nothing installed would be gone for the sake of one dataclass.

Three things this service is careful about, all of them about not overstating what was
found.

**Nothing is fabricated when nothing is configured.** A deployment with no API keys
gets a dossier whose claims all have empty ``sources`` and whose
:attr:`~app.domain.research.Dossier.searched` is ``False``. It does not raise, because
"the web was searched and holds nothing about this" and "no search happened" are
opposite findings that a 500 would flatten into the same non-answer — and it does not
pretend, because a consumer reading empty sources without checking ``searched`` would
report an expired key as an absence of evidence.

**A claim that was not researched is named.** Two things cause that — the extractor
marked it unfit to check, or the per-request claim ceiling cut it off — and both are
reported on :attr:`~app.domain.research.Dossier.skipped` with the reason
rather than being absent. A response
listing three claims for a submission that made twelve is a misdescription of the
submission, whatever the reason for the nine.

**One clock.** ``retrieved_at`` is read once and passed to the fan-out, to every
provider client, and to the dating in :mod:`app.research.dossier`. Brave returns
relative ages — ``"2 days ago"`` — so two reads of the clock would resolve two
providers' answers about the same page to two different dates.

**Fact checks are evidence, not a verdict.** The fact-check lookup runs beside the
search rather than after it, and what it finds is attached to
:attr:`~app.domain.research.ClaimResearch.fact_checks` — beside the web sources, not
folded into them and not summarised into a rating for the claim. This service never
resolves two fact-checkers who disagree, never counts them, and never lets one stand
in for the dossier's own finding. What a fact-checker concluded is a fact about a
published review; whether the claim is true is a separate question that the desks
answer with this as one input.

**Credibility grades the source, never the claim.** Each claim's sources are read on
the six axes of :mod:`app.domain.credibility` — who is accountable for the page,
whether the publisher holds the record, what is known about the date, whether this is
another copy of the source above it — and the readings go on
:attr:`~app.domain.research.ClaimResearch.credibility`, beside the sources rather
than on them, for the reason the fact checks are: a source carries what a provider
returned, and these numbers are this service's own. Nothing is reordered, dropped or
rescored by them; a grade that decided which sources a desk ever saw would be a
judgement made where nobody could see it. The scorer cannot read configuration — no
module in :mod:`app.research` may — so the two age windows are read here and passed
in explicitly, against the same ``retrieved_at`` as everything else.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING

from app.core.config import Settings
from app.core.logging import get_logger
from app.domain import Band, ClaimResearch, Dossier, ExtractedClaim, SkippedClaim
from app.factcheck.lookup import check
from app.research import credibility, dossier, queries, reviews
from app.search.fanout import Task, harvest
from app.services.claims import ClaimExtractionService
from app.services.limits import ensure_within_limit
from app.utils.clock import utcnow

if TYPE_CHECKING:
    # Only a type here. Importing it at runtime would pull in
    # `app.repositories.sql` and SQLAlchemy, which this service does not otherwise
    # need — the store is injected, and a caller that passes none never touches it.
    from app.repositories.base import ResearchRepository

logger = get_logger(__name__)


class WebResearchService:
    """Searches the web for a batch of claims and assembles what it finds."""

    def __init__(
        self,
        *,
        settings: Settings,
        extractor: ClaimExtractionService,
        store: ResearchRepository | None = None,
    ) -> None:
        self._settings = settings
        self._extractor = extractor
        self._store = store

    async def from_text(
        self, text: str, *, verification_id: str | None = None
    ) -> Dossier:
        """Extract the claims ``text`` makes, then research the checkable ones.

        Unfit claims are not searched. The extractor marks a clause unfit when it
        asserts nothing checkable — pure opinion, a question, a prediction — and
        spending three queries against three providers on "the policy was a disgrace"
        buys nothing. They come back on
        :attr:`~app.domain.research.Dossier.skipped` carrying the
        extractor's own reason, so a caller that disagrees with the judgement can see
        it was made and resubmit through the ``claims`` path, which does not second-
        guess the caller.

        Needs the NLP extras. :meth:`from_claims` is the path that does not.
        """
        extraction = await self._extractor.extract(text)
        unfit = tuple(
            SkippedClaim(
                claim=claim.text, reason=claim.reason or "not a checkable claim"
            )
            for claim in extraction.claims
            if not claim.checkable
        )
        checked = await self.from_extracted(
            [claim for claim in extraction.claims if claim.checkable],
            verification_id=verification_id,
        )
        # Unfit first, then anything the ceiling dropped: the order the two exclusions
        # were applied in, which is the order a reader reconstructing the request needs.
        return replace(checked, skipped=unfit + checked.skipped)

    async def from_claims(
        self, claims: Sequence[str], *, verification_id: str | None = None
    ) -> Dossier:
        """Research claims exactly as the caller wrote them.

        No extraction, so no spaCy, and no entities or keywords either — which means
        :func:`app.research.queries.build` has only the first rung to offer and each
        claim is searched as written and nothing else. That is a narrower search than
        the ``text`` path performs, and it is visible in the ``queries`` on the
        response rather than hidden.

        Nothing here judges whether the input is checkable. The caller asserting that
        this string is a claim is better evidence than a regex, and refusing to search
        for something a caller explicitly asked about would be this service overruling
        it on a guess.
        """
        ensure_within_limit(
            "\n".join(claims), limit=self._settings.MAX_TEXT_CHARS, field="claims"
        )
        extracted = [
            ExtractedClaim(
                ref=index,
                text=claim.strip(),
                # The caller's string *is* the source text here, so the span covers
                # all of it. ``quote`` is what the claim was read out of, and on this
                # path nothing was read: the two are the same string, which keeps the
                # ``text[start:end] == quote`` invariant true rather than filling the
                # offsets with something that would break it.
                quote=claim.strip(),
                start=0,
                end=len(claim.strip()),
            )
            for index, claim in enumerate(claims, start=1)
        ]
        return await self.from_extracted(extracted, verification_id=verification_id)

    async def from_extracted(
        self, claims: Sequence[ExtractedClaim], *, verification_id: str | None = None
    ) -> Dossier:
        """Search every configured provider for every claim, and report the result.

        Claims are researched in one fan-out rather than one at a time, so a batch
        costs one round of provider connections instead of *n*. The results stay
        separated by claim throughout — :attr:`app.search.fanout.Harvest.retrievals`
        is aligned by index, not keyed by claim text, because two claims in one
        request can be identical after rewriting and keying would silently drop one.

        Truncated to ``SEARCH_MAX_CLAIMS``, with everything past the ceiling returned
        on :attr:`~app.domain.research.Dossier.skipped`. The first *n* are kept
        rather than a sample: they are the
        ones the submission led with, and any other rule would need a notion of which
        claims matter that this service does not have.

        Never raises for a provider problem. Every provider's fate is a
        :class:`~app.domain.research.ProviderOutcome` on the dossier, including "no key
        configured" and "it returned a 500", because a caller needs to distinguish
        those from an honest empty result and an exception cannot carry that
        distinction alongside the results that did arrive.
        """
        ceiling = self._settings.SEARCH_MAX_CLAIMS
        researching, over = list(claims[:ceiling]), list(claims[ceiling:])
        dropped = tuple(
            SkippedClaim(
                claim=claim.text,
                reason=(
                    f"only the first {ceiling} claims of {len(claims)} were researched "
                    f"(SEARCH_MAX_CLAIMS={ceiling})"
                ),
            )
            for claim in over
        )

        retrieved_at = utcnow()
        built = [
            queries.build(claim, limit=self._settings.SEARCH_QUERIES_PER_CLAIM)
            for claim in researching
        ]
        # Concurrently, because the two ask different services nothing about each
        # other and the lookup is one request per claim: serialising it behind nine
        # search requests would add a round trip to every dossier for no reason.
        # `gather` without `return_exceptions` is right here — both of these already
        # convert every provider failure into an outcome, so an exception escaping one
        # of them is a bug in this application, not a provider having a bad day, and
        # swallowing it would hide the bug behind an empty section.
        found, checked = await asyncio.gather(
            harvest(
                [
                    Task(claim=claim.text, queries=formulations)
                    for claim, formulations in zip(researching, built, strict=True)
                ],
                settings=self._settings,
                now=retrieved_at,
            ),
            check(
                [claim.text for claim in researching],
                settings=self._settings,
                now=retrieved_at,
            ),
        )

        researched = tuple(
            self._graded(
                dossier.for_claim(
                    claim,
                    queries=built[index],
                    retrievals=found.retrievals[index],
                    fact_checks=reviews.select(
                        claim,
                        checked.found[index],
                        source=str(self._settings.FACT_CHECK_PROVIDER),
                        min_match=self._settings.FACT_CHECK_MIN_MATCH,
                    ),
                    now=retrieved_at,
                ),
                now=retrieved_at,
            )
            for index, claim in enumerate(researching)
        )
        result = Dossier(
            claims=researched,
            providers=found.outcomes,
            retrieved_at=retrieved_at,
            skipped=dropped,
            fact_checkers=checked.outcomes,
        )

        logger.info(
            "web research complete",
            extra={
                "claims": len(researched),
                "skipped": len(dropped),
                "sources": sum(len(c.sources) for c in researched),
                "domains": len({d for c in researched for d in c.domains}),
                "stories": sum(c.stories for c in researched),
                "searched": result.searched,
                "fact_checks": result.fact_checks,
                "fact_checked": result.fact_checked,
                # Which providers answered, so a thin dossier can be explained from
                # the log without reproducing the request.
                "outcomes": {o.provider: str(o.status) for o in found.outcomes},
                "fact_checkers": {o.provider: str(o.status) for o in checked.outcomes},
                # How the sources graded, counted by band. Cheap — the readings are
                # already computed — and the one thing about the scoring worth having
                # in a log: a dossier that is all ``unknown`` is a scorer reaching
                # nothing, which is invisible from the counts above. No URL and no
                # claim text: a log line is not a place to reproduce the request.
                "credibility": _bands(researched),
            },
        )
        await self._persist(result, verification_id=verification_id)
        return result

    async def _persist(
        self, assembled: Dossier, *, verification_id: str | None
    ) -> None:
        """Write the dossier, if there is a store, without failing the research.

        A storage problem must not turn a dossier that was successfully assembled
        into an error: the claims were researched, the sources were found, and the
        caller can have them whether or not a row was written. The failure is logged
        rather than raised for the same reason the fan-out converts a provider error
        into an outcome — losing the result in order to report the write would be
        the worse of the two outcomes.

        The parameter is not called ``dossier``: :mod:`app.research.dossier` is
        imported under that name in this module.
        """
        if self._store is None:
            return
        try:
            await self._store.save_dossier(assembled, verification_id=verification_id)
        except Exception:
            logger.exception(
                "research could not be stored",
                extra={"verification_id": verification_id},
            )

    def _graded(self, research: ClaimResearch, *, now: datetime) -> ClaimResearch:
        """``research`` with a credibility reading beside each of its sources.

        Attached after :func:`app.research.dossier.for_claim` rather than inside it. A
        reading carries the :attr:`~app.domain.research.Source.ref` it belongs to, so it
        can only be made once the sources are ordered and numbered; and the two windows
        below are configuration, which no module in :mod:`app.research` may read.
        Threading them through the assembly to reach the scorer would put settings in
        the one package that is deliberately free of them.

        ``now`` is the dossier's ``retrieved_at`` rather than a fresh reading, so a
        page's age is measured from the same instant its date was resolved against.
        Two clocks would let one source be fresh for the dating and stale for the
        grading.

        Off means an empty tuple and nothing else: no source is dropped, reordered or
        rescored either way, because this is reported beside the sources and never
        applied to them.
        """
        if not self._settings.CREDIBILITY_ENABLED:
            return research
        return replace(
            research,
            credibility=credibility.rate(
                research.sources,
                now=now,
                fresh_days=self._settings.CREDIBILITY_FRESH_DAYS,
                stale_days=self._settings.CREDIBILITY_STALE_DAYS,
            ),
        )


def _bands(claims: Sequence[ClaimResearch]) -> dict[str, int]:
    """How the graded sources across the dossier fall into bands, for the log line.

    Every band is reported, zeros included, so the shape of the entry does not change
    between requests and a collector can chart it. All zeros is what a dossier with no
    sources looks like, and also what one looks like with the grading switched off.
    """
    counted = Counter(record.band for claim in claims for record in claim.credibility)
    return {band.value: counted[band] for band in Band}
