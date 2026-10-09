"""Test doubles for the desk and claim-extraction seams.

Only the image desk is implemented, so anything that tests the
orchestration across several desks has to supply the rest. These are stubs, not
implementations: each returns a report it was handed or a canned one, and none of
them examines anything. They live here rather than in ``conftest.py`` because they
are classes two modules construct differently, not fixtures.

:func:`desk_bench` and :func:`extractor_bench` are the important pieces. The
registries in :mod:`app.desks` and :mod:`app.nlp` are module-level singletons, so a
stub left registered after a test would make a later test pass for the wrong reason —
the hardest kind of failure to trace back. The context managers make the cleanup
unconditional, and both restore what they displaced rather than clearing the key:
``app.nlp`` registers a real extractor at import and ``app.desks`` now registers
a real image examiner, and unregistering it would leave the seam
emptier than it was found and turn every later test in the session into a 501.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager

from app.core.config import ClaimExtractorProvider
from app.desks import ArtifactDesk, adjudicators, examiners
from app.domain import (
    ADJUDICATOR,
    Annotation,
    Artifact,
    ArtifactKind,
    Desk,
    DeskReport,
    Determination,
    Entity,
    Exhibit,
    ExtractedClaim,
    Extraction,
    Keyword,
    LedgerEntry,
    Relevance,
    Reliability,
    Signal,
    Unfit,
    Verdict,
)
from app.nlp import claim_extractors
from app.nlp.pipeline import build as build_spacy_extractor


def canned(
    desk: Desk, determination: Determination = Determination.SUPPORTED
) -> DeskReport:
    """The smallest valid report: a verdict and one ledger row."""
    return DeskReport(
        desk=desk,
        verdict=Verdict(
            determination=determination,
            headline=f"{desk.value} reporting",
            rationale="Canned.",
            confidence=0.5,
        ),
        ledger=(LedgerEntry(key="Desk", value=desk.value),),
    )


def furnished(desk: Desk) -> DeskReport:
    """A report with every optional collection populated.

    Used by the HTTP tests, where the point is to drive every ``from_domain`` adapter
    at least once — a report with empty lists would leave most of them unexercised and
    a mistyped field name inside one invisible.
    """
    return DeskReport(
        desk=desk,
        verdict=Verdict(
            determination=Determination.CONTESTED,
            headline="Two records disagree",
            rationale="The opening date is given differently by each.",
            confidence=0.75,
        ),
        ledger=(LedgerEntry(key="Sources", value="2"),),
        annotations=(
            Annotation(
                ref=1,
                quote="opened in March",
                note="The date is contested.",
                determination=Determination.CONTESTED,
            ),
        ),
        signals=(Signal(label="Source agreement", reading="Split", weight=0.5),),
        exhibits=(
            Exhibit(
                ref=1,
                source="Example Wire",
                published="2026-03-04",
                relevance=Relevance.HIGH,
                reliability=Reliability.VERIFIED,
                determination=Determination.CONTRADICTED,
                extract="The bridge opened in April.",
            ),
        ),
    )


class StubExaminer:
    """Files a given report, or raises what it was told to raise."""

    def __init__(
        self,
        desk: Desk,
        *,
        report: DeskReport | None = None,
        raises: Exception | None = None,
    ) -> None:
        self.desk = desk
        self.kinds = frozenset(ArtifactKind)
        self._report = report
        self._raises = raises
        #: Every artifact handed to this desk, so a test can assert it was the one
        #: submitted rather than a copy assembled somewhere in between.
        self.seen: list[Artifact] = []
        #: The record id each examination was told it belonged to. A desk that
        #: persists evidence needs it, so the orchestrator passing it is a contract
        #: worth asserting rather than an argument that happens to be accepted.
        self.records: list[str | None] = []

    async def examine(
        self, artifact: Artifact, *, verification_id: str | None = None
    ) -> DeskReport:
        self.seen.append(artifact)
        self.records.append(verification_id)
        if self._raises is not None:
            raise self._raises
        return self._report if self._report is not None else canned(self.desk)


class StubAdjudicator:
    """Records what it was handed, so the service's re-read can be checked."""

    def __init__(
        self,
        *,
        report: DeskReport | None = None,
        determination: Determination = Determination.CONTESTED,
    ) -> None:
        self.desk = ADJUDICATOR
        self._report = report
        self._determination = determination
        self.seen: list[tuple[DeskReport, ...]] = []

    async def adjudicate(self, reports: Sequence[DeskReport]) -> DeskReport:
        self.seen.append(tuple(reports))
        if self._report is not None:
            return self._report
        return canned(ADJUDICATOR, self._determination)


@contextmanager
def desk_bench(
    examining: Mapping[Desk, ArtifactDesk],
    adjudicator: StubAdjudicator | None = None,
) -> Iterator[None]:
    """Register the given desks for the duration of the block, then put back what
    was there.

    Typed to the protocol rather than to :class:`StubExaminer`, because the same
    swap is what an end-to-end test needs in order to seat a *real* desk carrying
    injected collaborators — see ``test_pipeline_contracts.py``.

    Restoring rather than unregistering, because the registries are not uniformly
    empty any more: ``Desk.IMAGE`` has a real examiner registered at import.
    Unregistering it would leave the seam emptier than this found it and turn every
    later resolve in the session into a 501.
    """
    was = {desk: examiners.factory(desk) for desk in examining}
    for desk, stub in examining.items():
        examiners.register(desk, lambda stub=stub: stub)
    if adjudicator is not None:
        adjudicators.register(ADJUDICATOR, lambda: adjudicator)
    try:
        yield
    finally:
        for desk, previous in was.items():
            if previous is None:
                examiners.unregister(desk)
            else:
                examiners.register(desk, previous)
        if adjudicator is not None:
            adjudicators.unregister(ADJUDICATOR)


# --------------------------------------------------- claim extraction ----


def sample_extraction() -> Extraction:
    """An extraction with every field populated, including an unfit claim.

    Populated rather than minimal for the same reason :func:`furnished` is: the HTTP
    tests exist to drive every ``from_domain`` adapter at least once, and empty lists
    would leave ``EntityOut`` and ``KeywordOut`` unexercised and a mistyped field name
    inside either one invisible.

    The offsets are real — they index the string :data:`SAMPLE_TEXT` — so a test can
    assert the ``source[start:end] == quote`` invariant against something rather than
    just check the numbers are integers.
    """
    return Extraction(
        claims=(
            ExtractedClaim(
                ref=1,
                text="The bridge opened in March 2026.",
                quote="The bridge opened in March 2026",
                start=0,
                end=31,
                entities=(Entity(text="March 2026", label="DATE", start=21, end=31),),
                keywords=(Keyword(term="bridge", score=1.0),),
            ),
            ExtractedClaim(
                ref=2,
                text="It is a beautiful bridge.",
                quote="It is a beautiful bridge",
                start=33,
                end=57,
                checkable=False,
                reason=Unfit.OPINION,
            ),
        ),
        entities=(Entity(text="March 2026", label="DATE", start=21, end=31),),
        keywords=(Keyword(term="bridge", score=1.0), Keyword(term="march", score=0.5)),
        sentences=2,
    )


#: The prose :func:`sample_extraction`'s offsets refer to.
SAMPLE_TEXT = "The bridge opened in March 2026. It is a beautiful bridge."


class StubClaimExtractor:
    """Returns a canned extraction, or raises what it was told to raise.

    Exists so the endpoint and the service can be tested with no NLP library
    installed at all — which is the property :mod:`app.nlp` keeps its imports inside
    function bodies to preserve, and this is the thing that would break first if that
    discipline ever slipped.
    """

    def __init__(
        self,
        *,
        extraction: Extraction | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._extraction = extraction
        self._raises = raises
        #: Every string handed to this extractor, so a test can assert the service
        #: passed the text through rather than a normalised copy of it.
        self.seen: list[str] = []

    async def extract(self, text: str) -> Extraction:
        self.seen.append(text)
        if self._raises is not None:
            raise self._raises
        if self._extraction is not None:
            return self._extraction
        return sample_extraction()


@contextmanager
def extractor_bench(extractor: StubClaimExtractor) -> Iterator[None]:
    """Substitute ``extractor`` for the real one, and put the real one back after.

    Restores rather than unregisters: :mod:`app.nlp` registers the spaCy extractor at
    import time, so removing the key would leave the seam broken for the rest of the
    session. Re-registering the same factory the package registered is what makes
    this a substitution and not a demolition.
    """
    claim_extractors.register(ClaimExtractorProvider.SPACY, lambda _settings: extractor)
    try:
        yield
    finally:
        claim_extractors.register(ClaimExtractorProvider.SPACY, build_spacy_extractor)
