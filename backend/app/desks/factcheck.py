"""The fact-check desk: run the graph, publish what it found, store the gathering.

This desk is the pipeline with nothing in front of it. The image desk
recovers text and hands it here; a submitted string arrives here directly. Everything
between the claim and the verdict —
:class:`~app.services.claims.ClaimExtractionService`, web search, the fact-check
lookup, evidence selection, source credibility, contradiction detection, the judge,
and the reasoning layer after them — happens inside
:class:`app.graph.workflow.VerificationGraph`. What is left for this module is the
three things the graph deliberately does not do:

**Retrieval.** :class:`app.services.evidence.EvidenceIndex` indexes this run's
passages and reads them back by vector distance. It is a *second reading of what was
already gathered* and it changes no finding: it decides which passage of a source a
reader is shown and in what order the sources are listed. Nothing retrieved can
enter the ruling, because the ruling is already made by the time this runs.

**Exhibits.** Every determination beside a source is derived from the judge's own
indications, matched to the source by :attr:`app.graph.verdict.Indication.ref`, and
never re-derived from the passages here. Two modules reading the same evidence and
reaching their own conclusions is how a record comes to contradict itself.

**Persistence.** The dossier the graph assembled is written through
:class:`app.repositories.base.ResearchRepository`, which is the only reason
``verification_id`` reaches a desk at all. A storage failure is logged and the report
is still filed — the claims were checked whether or not a row was written.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from app.core.config import Settings, StoreBackend, get_settings
from app.core.errors import VeritasError
from app.desks.anchors import note
from app.desks.graph import compiled, model_ledger, readings
from app.domain import (
    Annotation,
    Artifact,
    ArtifactKind,
    Band,
    Credibility,
    DateBasis,
    Desk,
    DeskReport,
    Determination,
    Exhibit,
    LedgerEntry,
    ProviderStatus,
    Relevance,
    Reliability,
    Signal,
    Source,
    Verdict,
)
from app.graph.state import Case, cases, dossier
from app.graph.verdict import Bearing, ClaimRuling, Ruling, as_determination
from app.reasoning.answer import Reasoning
from app.research.terms import squeeze
from app.media import fetch

if TYPE_CHECKING:
    from app.graph.workflow import Outcome, VerificationGraph
    from app.repositories.base import ResearchRepository
    from app.services.evidence import EvidenceIndex
    from app.vectorstore.evidence import Relevant

logger = logging.getLogger(__name__)

__all__ = ["FactCheckDesk", "build"]

#: How much of a source's title is printed in the exhibit ledger. The column is one
#: line in ``ExhibitLedger.tsx`` and a full headline with a masthead appended wraps
#: over the determination beneath it.
TITLE_LIMIT = 90

#: Reliability from the source's credibility band.
#:
#: :attr:`~app.domain.enums.Reliability.VERIFIED` is absent and unreachable. It means
#: the record itself was reached — a primary document rather than a report of one —
#: and nothing in this pipeline reaches a primary record: every source here is a
#: search result. Leaving it unassignable is the structural form of "do not treat any
#: domain as automatically true", since VERIFIED is exactly the value a reader would
#: read as settled.
#:
#: :attr:`~app.domain.Band.UNKNOWN` maps to LOW because ``Reliability`` has no member
#: for "not established", and of the four it is the only one that cannot overstate
#: what is known. It is a floor, not a finding about the publisher —
#: :attr:`app.domain.Credibility.coverage` is what says how much could be assessed,
#: and it travels with the dossier.
_RELIABILITY: dict[Band, Reliability] = {
    Band.STRONG: Reliability.HIGH,
    Band.MODERATE: Reliability.MEDIUM,
    Band.WEAK: Reliability.LOW,
    Band.UNKNOWN: Reliability.LOW,
}

#: How each kind of date is written. A publisher's stated publication date is printed
#: plainly; everything weaker is qualified in the cell itself, because
#: :class:`app.domain.DateBasis` draws the distinction and a bare date on the wire
#: would throw it away — "by" for a date that may be a modification, "c." for one
#: resolved from a relative age, and the URL named when no provider stated anything.
_DATED: dict[DateBasis, str] = {
    DateBasis.PROVIDER: "{date}",
    DateBasis.PROVIDER_MODIFIED: "by {date}",
    DateBasis.PROVIDER_RELATIVE: "c. {date}",
    DateBasis.URL_PATH: "{date}, from the URL",
}

UNDATED = "date not stated"


class FactCheckDesk:
    """Checks what a submission asserts against what can be found about it."""

    desk = Desk.FACT_CHECK
    kinds = frozenset({ArtifactKind.TEXT, ArtifactKind.CLAIM, ArtifactKind.URL})

    def __init__(
        self,
        *,
        settings: Settings,
        graph: VerificationGraph | None = None,
        index: EvidenceIndex | None = None,
        store: ResearchRepository | None = None,
    ) -> None:
        self._settings = settings
        self._own_graph = graph
        self._own_index = index
        self._store = store

    async def examine(
        self, artifact: Artifact, *, verification_id: str | None = None
    ) -> DeskReport:
        copy, fetch_error = await self._copy(artifact)
        if not copy.strip():
            return self._unread(artifact.kind, fetch_error)

        # Keep the original URL on the record while handing the fetched page copy to
        # the graph. This lets the URL page show its source address and still checks
        # the claims actually published at that address.
        outcome = await self._graph().run(
            artifact if artifact.content else Artifact(
                # The graph's claim extractor accepts prose and claims. The URL is
                # retained as provenance, but the fetched page itself is text.
                kind=ArtifactKind.TEXT,
                content=copy,
                url=artifact.url,
                filename=artifact.filename,
            )
        )
        found = cases(outcome.state)
        retrieved, indexed = await self._retrieved(found)
        await self._stored(outcome, verification_id=verification_id)
        return self._filed(outcome, found, retrieved, indexed)

    async def _copy(self, artifact: Artifact) -> tuple[str, str | None]:
        if artifact.content:
            return artifact.content, None
        if artifact.kind is not ArtifactKind.URL or not artifact.url:
            return "", None
        try:
            return (
                await fetch.fetch_text(
                    artifact.url,
                    timeout=self._settings.MEDIA_FETCH_TIMEOUT_SECONDS,
                    limit=self._settings.MAX_UPLOAD_BYTES,
                    max_chars=self._settings.MAX_TEXT_CHARS,
                    allow_private=self._settings.MEDIA_ALLOW_PRIVATE_HOSTS,
                ),
                None,
            )
        except VeritasError as exc:
            return "", exc.message

    # ------------------------------------------------------------ steps ----

    def _graph(self) -> VerificationGraph:
        return self._own_graph or compiled(self._settings)

    async def _retrieved(
        self, found: Sequence[Case]
    ) -> tuple[dict[int, tuple[Relevant, ...]], int]:
        """Index this run's passages and read them back, or degrade to neither.

        An index this desk built is closed here; one passed in belongs to the caller
        and is left open. Both a store that cannot be opened and a query that fails
        are losses of ordering, not of findings, so neither is allowed to fail the
        examination.
        """
        if not self._settings.EVIDENCE_INDEX_ENABLED:
            return {}, 0

        if self._own_index is not None:
            return await self._read(self._own_index, found)

        from app.services import evidence

        try:
            index = evidence.build(self._settings)
        except VeritasError as exc:
            logger.warning("evidence index unavailable: %s", exc.message)
            return {}, 0

        try:
            return await self._read(index, found)
        finally:
            await index.aclose()

    async def _read(
        self, index: EvidenceIndex, found: Sequence[Case]
    ) -> tuple[dict[int, tuple[Relevant, ...]], int]:
        retrieved: dict[int, tuple[Relevant, ...]] = {}
        indexed = 0
        for case in found:
            if case.research is None:
                continue
            try:
                indexed += await index.index(case.research)
                retrieved[case.claim.ref] = await index.relevant(case.research.claim)
            except Exception:
                logger.exception(
                    "evidence retrieval failed for one claim",
                    extra={"ref": case.claim.ref},
                )
        return retrieved, indexed

    async def _stored(self, outcome: Outcome, *, verification_id: str | None) -> None:
        """Write what was gathered, without letting a write failure lose it."""
        if self._store is None:
            return
        try:
            await self._store.save_dossier(
                dossier(outcome.state), verification_id=verification_id
            )
        except Exception:
            logger.exception(
                "the dossier could not be stored",
                extra={"verification_id": verification_id},
            )

    # ----------------------------------------------------------- filing ----

    def _unread(self, kind: ArtifactKind, fetch_error: str | None = None) -> DeskReport:
        missing = (
            "A link was submitted, but the page could not be read. "
            f"{fetch_error or 'The page returned no readable prose.'}"
            if kind is ArtifactKind.URL
            else "The submission carried nothing to check."
        )
        return DeskReport(
            desk=self.desk,
            verdict=Verdict(
                determination=Determination.INSUFFICIENT,
                headline="Nothing was checked",
                rationale=f"{missing} No source was searched for and none was found.",
                confidence=0.0,
            ),
            ledger=(LedgerEntry("Claims checked", "0"),),
        )

    def _filed(
        self,
        outcome: Outcome,
        found: Sequence[Case],
        retrieved: Mapping[int, tuple[Relevant, ...]],
        indexed: int,
    ) -> DeskReport:
        ruling = outcome.ruling
        rulings = {claim.ref: claim for claim in ruling.claims}
        exhibits, dropped = _exhibits(
            found, retrieved, rulings, limit=self._settings.EVIDENCE_TOP_K
        )
        return DeskReport(
            desk=self.desk,
            verdict=Verdict(
                determination=as_determination(ruling.judgement),
                headline=ruling.headline,
                rationale=_rationale(ruling, found),
                confidence=ruling.confidence,
            ),
            ledger=(
                *_ledger(outcome, found, indexed=indexed, dropped=dropped),
                *model_ledger(outcome.reasoning),
            ),
            annotations=claim_annotations(outcome),
            signals=_signals(found, ruling, retrieved),
            exhibits=exhibits,
        )


# ------------------------------------------------------------------ exhibits ---


def evidence_exhibits(outcome: Outcome, limit: int = 8) -> tuple[Exhibit, ...]:
    return _exhibits(
        cases(outcome.state), {}, {r.ref: r for r in outcome.ruling.claims}, limit=limit
    )[0]


def claim_annotations(outcome: Outcome) -> tuple[Annotation, ...]:
    checked = _annotations(
        cases(outcome.state),
        {r.ref: r for r in outcome.ruling.claims},
        readings(outcome.ruling.claims, outcome.reasoning),
    )
    start = max((a.ref for a in checked), default=0) + 1
    artifact = outcome.state.get("artifact")
    copy = artifact.content or "" if artifact else ""
    skipped = tuple(
        Annotation(
            ref=start + n,
            quote=item.claim if item.claim in copy else "",
            note=f"Not checked: {item.claim} — {item.reason}",
            determination=Determination.INSUFFICIENT,
        )
        for n, item in enumerate(outcome.state.get("skipped", ()))
    )
    return (*checked, *skipped)


def _exhibits(
    found: Sequence[Case],
    retrieved: Mapping[int, tuple[Relevant, ...]],
    rulings: Mapping[int, ClaimRuling],
    *,
    limit: int,
) -> tuple[tuple[Exhibit, ...], int]:
    """One exhibit per source, claim by claim, and how many did not fit.

    Grouped by claim rather than sorted across all of them, because the refs a reader
    follows have to run in the order the record reads. Within a claim the order is
    the retrieval's: a passage that restates the claim in other words ranks above one
    that merely repeats its topic words, which is the ranking lexical selection
    cannot produce and the only thing retrieval is used for here.
    """
    exhibits: list[Exhibit] = []
    dropped = 0
    for case in found:
        nearest = _nearest(retrieved.get(case.claim.ref, ()))
        ordered = _ordered(case.sources, nearest)
        claim_ruling = rulings.get(case.claim.ref)
        bearings = _bearings(claim_ruling)
        cited = (
            {i.ref: i.quote for i in claim_ruling.indications if i.ref and i.quote}
            if claim_ruling
            else {}
        )
        ordered.sort(key=lambda s: s.ref not in cited)
        for source in ordered[:limit]:
            _, quote = nearest.get(source.ref, (0.0, ""))
            exhibits.append(
                Exhibit(
                    ref=len(exhibits) + 1,
                    source=_named(source),
                    published=_published(source),
                    relevance=_relevance(source),
                    reliability=_reliability(case.credibility_of(source.ref)),
                    determination=_bears(bearings.get(source.ref, frozenset()), source),
                    extract=cited.get(source.ref) or quote or _extract(source),
                    url=source.url,
                    claim_ref=case.claim.ref,
                )
            )
        dropped += max(0, len(ordered) - limit)
    return tuple(exhibits), dropped


def _ordered(
    sources: Sequence[Source], nearest: Mapping[int, tuple[float, str]]
) -> list[Source]:
    """Sources by how closely retrieval placed them, ties broken by dossier order."""
    return sorted(sources, key=lambda s: (-nearest.get(s.ref, (0.0, ""))[0], s.ref))


def _nearest(relevant: Sequence[Relevant]) -> dict[int, tuple[float, str]]:
    """The closest retrieved passage for each source, by source ref.

    A passage is credited to every source that carried it, not only the one the
    store returned it under: :attr:`app.vectorstore.evidence.Relevant.refs` is the
    index's own record that several pages held the same sentence, and dropping the
    rest would order a syndicated report above the wire copy it came from by
    accident.
    """
    best: dict[int, tuple[float, str]] = {}
    for passage in relevant:
        for ref in passage.refs or (passage.ref,):
            current = best.get(ref)
            if current is None or passage.similarity > current[0]:
                best[ref] = (passage.similarity, passage.quote)
    return best


def _bearings(ruling: ClaimRuling | None) -> dict[int, frozenset[Bearing]]:
    """Which way each source was taken to bear, as the judge recorded it."""
    if ruling is None:
        return {}
    found: dict[int, set[Bearing]] = {}
    for indication in ruling.indications:
        if indication.ref is not None:
            found.setdefault(indication.ref, set()).add(indication.bearing)
    return {ref: frozenset(bearings) for ref, bearings in found.items()}


def _bears(bearings: frozenset[Bearing], source: Source) -> Determination:
    """What this source did to the claim, and nothing stronger.

    A source the arithmetic never weighed reads as CONSISTENT when it carried a
    passage on the claim and REQUIRES_VERIFICATION when it did not — never SUPPORTED,
    which would report a page as confirming a claim on the strength of appearing in
    the same search results.
    """
    if Bearing.SUPPORTS in bearings and Bearing.REFUTES in bearings:
        return Determination.CONTESTED
    if Bearing.REFUTES in bearings:
        return Determination.CONTRADICTED
    if Bearing.SUPPORTS in bearings:
        return Determination.SUPPORTED
    if source.evidence:
        return Determination.CONSISTENT
    return Determination.REQUIRES_VERIFICATION


def _relevance(source: Source) -> Relevance:
    """How directly the page bears on the claim, from what its passages repeated.

    Read across every passage rather than the strongest one: evidence is ordered by
    lexical score, and a page's second passage is where its figure usually sits.
    """
    if not source.evidence:
        return Relevance.LOW
    if any(p.matched_numbers or p.matched_entities for p in source.evidence):
        return Relevance.HIGH
    if any(p.matched_terms for p in source.evidence):
        return Relevance.MEDIUM
    return Relevance.LOW


def _reliability(grade: Credibility | None) -> Reliability:
    """See :data:`_RELIABILITY`. An ungraded source is floored, never promoted."""
    return _RELIABILITY[grade.band] if grade is not None else Reliability.LOW


def _named(source: Source) -> str:
    title = squeeze(source.title)
    if not title:
        return source.domain
    return f"{_clipped(title, TITLE_LIMIT)} ({source.domain})"


def _published(source: Source) -> str:
    if source.published_at is None or source.date_basis is None:
        return UNDATED
    stamped = source.published_at.strftime("%d %b %Y")
    return _DATED[source.date_basis].format(date=stamped)


def _extract(source: Source) -> str:
    """The strongest passage this page carried, or a statement that it carried none.

    Never the page's first sentence as a substitute. An arbitrary line presented in
    an evidence column is a fabrication of relevance even though every character of
    it is real — the same rule :class:`app.domain.Source` follows in leaving
    ``evidence`` empty.
    """
    if source.evidence:
        return source.evidence[0].quote
    return "No passage in this page bears on the claim."


# -------------------------------------------------------------------- filing ---


def _annotations(
    found: Sequence[Case],
    rulings: Mapping[int, ClaimRuling],
    read: Mapping[int, Reasoning],
) -> tuple[Annotation, ...]:
    """One marked claim per ruling, quoting the submission verbatim.

    ``quote`` is :attr:`app.domain.ExtractedClaim.quote` rather than the rewritten
    ``text`` the graph searched on. The rewrite resolves pronouns and carries
    subjects into clauses, so it is frequently not a substring of what was submitted
    — and the frontend locates a marked span with ``indexOf``.
    """
    marked = []
    for case in found:
        ruling = rulings.get(case.claim.ref)
        if ruling is None:
            continue
        marked.append(
            Annotation(
                ref=ruling.ref,
                quote=case.claim.quote or ruling.claim,
                note=note(ruling, read.get(ruling.ref)),
                determination=as_determination(ruling.judgement),
            )
        )
    return tuple(marked)


def _rationale(ruling: Ruling, found: Sequence[Case]) -> str:
    """The judge's account, plus who else has already reviewed the claim.

    Published reviews are named here rather than given exhibits of their own. A
    reviewer's rating is somebody else's verdict, and an exhibit row would need a
    :class:`~app.domain.enums.Reliability` for a page this service has not graded —
    which would mean inventing standing for a domain in order to display it.
    """
    reviewed = {
        publisher
        for case in found
        for check in case.fact_checks
        for publisher in check.publishers
    }
    if not reviewed:
        return ruling.rationale
    return (
        f"{ruling.rationale} This claim has been reviewed before: "
        f"{', '.join(sorted(reviewed))}. Those ratings are weighed as evidence, not "
        f"adopted as the finding."
    )


def _ledger(
    outcome: Outcome,
    found: Sequence[Case],
    *,
    indexed: int,
    dropped: int,
) -> tuple[LedgerEntry, ...]:
    sources = [source for case in found for source in case.sources]
    providers = outcome.state.get("providers", ())
    answered = [
        o
        for o in providers
        if o.status in (ProviderStatus.SEARCHED, ProviderStatus.PARTIAL)
    ]
    reviews = sum(len(case.fact_checks) for case in found)
    skipped = outcome.state.get("skipped", ())

    entries = [
        LedgerEntry(
            "Checked at",
            outcome.state["now"].strftime("%d %b %Y, %H:%M UTC")
            if outcome.state.get("now")
            else "Not recorded",
        ),
        LedgerEntry("Claims checked", str(len(found))),
        LedgerEntry("Sources found", str(len(sources))),
        LedgerEntry("Publishers", str(len({s.domain for s in sources}))),
        LedgerEntry(
            "Independent stories",
            str(sum(case.research.stories for case in found if case.research)),
        ),
        LedgerEntry(
            "Search providers", f"{len(answered)} of {len(providers)} answered"
        ),
    ]
    if skipped:
        entries.append(LedgerEntry("Claims set aside", str(len(skipped))))
    if reviews:
        entries.append(LedgerEntry("Published reviews", str(reviews)))
    if indexed:
        entries.append(LedgerEntry("Passages indexed", str(indexed)))
    if dropped:
        entries.append(LedgerEntry("Sources not shown", str(dropped)))
    for provider in providers:
        if provider.status not in (ProviderStatus.SEARCHED, ProviderStatus.PARTIAL):
            entries.append(
                LedgerEntry(
                    f"Search: {provider.provider}",
                    provider.detail or str(provider.status),
                )
            )
    return tuple(entries)


def _signals(
    found: Sequence[Case],
    ruling: Ruling,
    retrieved: Mapping[int, tuple[Relevant, ...]],
) -> tuple[Signal, ...]:
    """Measurements only, each a genuine share of something counted.

    No signal here is a normalised score. A bar whose length came from dividing a
    weight by a number chosen to make it fit would be a judgement wearing a
    measurement's clothes, and every one of these is a ratio a reader could check
    against the ledger above it.
    """
    signals = []
    if ruling.claims:
        settled = sum(1 for c in ruling.claims if not c.insufficiency)
        signals.append(
            Signal(
                label="Claims settled",
                reading=f"{settled} of {len(ruling.claims)}",
                weight=round(settled / len(ruling.claims), 4),
            )
        )

    standings = [
        grade.standing
        for case in found
        for grade in case.grading
        if grade.standing is not None
    ]
    if standings:
        signals.append(
            Signal(
                label="Source standing",
                reading=f"mean of {len(standings)} graded source(s)",
                weight=round(sum(standings) / len(standings), 4),
            )
        )

    sources = sum(len(case.sources) for case in found)
    stories = sum(case.research.stories for case in found if case.research)
    if sources:
        signals.append(
            Signal(
                label="Independent reporting",
                reading=f"{stories} story/stories across {sources} source(s)",
                weight=round(stories / sources, 4),
            )
        )

    if retrieved:
        hit = sum(1 for passages in retrieved.values() if passages)
        signals.append(
            Signal(
                label="Evidence retrieved",
                reading=f"{hit} of {len(retrieved)} claim(s)",
                weight=round(hit / len(retrieved), 4),
            )
        )
    return tuple(signals)


def _clipped(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def build(settings: Settings | None = None) -> FactCheckDesk:
    """Factory for the registry, which resolves desks with no arguments.

    The store is resolved from the settings rather than injected, because desks are
    resolved without arguments and cannot be handed a request-scoped dependency. The
    rule is the one :func:`app.api.deps.get_research_store` applies: ``memory`` means
    do not persist, and ``None`` rather than a no-op store is what keeps "nothing was
    written" distinguishable from "it was written".
    """
    resolved = settings or get_settings()
    store: ResearchRepository | None = None
    if resolved.VERIFICATION_STORE is not StoreBackend.MEMORY:
        from app.repositories import SqlResearchRepository

        store = SqlResearchRepository()
    return FactCheckDesk(settings=resolved, store=store)
