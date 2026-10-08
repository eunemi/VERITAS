"""The text desk: read how a submission is written, and say what can be checked.

It does not rule on truth. That is the fact-check desk's work, and the two open on the
same artifact — :data:`app.domain.enums.DEFAULT_DESKS` sends copy to both — precisely
so the two readings stay separable. This desk answers "what does this document assert,
and which of those assertions could anyone check?"; the other answers "and are they
so?".

So every determination it files is either :attr:`~app.domain.Determination.INSUFFICIENT`
or :attr:`~app.domain.Determination.REQUIRES_VERIFICATION`, and never anything
affirmative. A desk that has checked nothing must not file a finding that reads as
though it had — see :data:`app.desks.decision.GRAVITY`, where that is also why
REQUIRES_VERIFICATION never outranks what the fact-check desk went on to find.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings, get_settings
from app.domain import (
    Annotation,
    Artifact,
    ArtifactKind,
    Desk,
    DeskReport,
    Determination,
    ExtractedClaim,
    Extraction,
    LedgerEntry,
    Signal,
    Verdict,
)

if TYPE_CHECKING:
    from app.services.claims import ClaimExtractionService

__all__ = ["TextDesk", "build"]

#: How much of a claim is quoted in a ledger line. The annotations carry the claims in
#: full; the ledger is a summary and a whole paragraph in it is not one.
LEDGER_QUOTE = 80


class TextDesk:
    """Extracts and screens the assertions in a submission."""

    desk = Desk.TEXT
    kinds = frozenset({ArtifactKind.TEXT, ArtifactKind.CLAIM, ArtifactKind.URL})

    def __init__(
        self, *, settings: Settings, extractor: ClaimExtractionService | None = None
    ) -> None:
        self._settings = settings
        self._own = extractor

    async def examine(
        self, artifact: Artifact, *, verification_id: str | None = None
    ) -> DeskReport:
        text = (artifact.content or "").strip()
        if not text:
            return self._unread(artifact.kind)

        # A caller who submitted a claim submitted the assertion itself, so there is
        # nothing to find in it. Taken as read here for the same reason
        # `app.graph.agents.claim` takes it as read: screening it would let this desk
        # set aside a claim the fact-check desk then goes on to check anyway.
        if artifact.kind is ArtifactKind.CLAIM:
            return self._submitted(text)

        return self._filed(await self._extractor().extract(text))

    def _extractor(self) -> ClaimExtractionService:
        # Imported here, not at module scope: `app.services` imports the
        # orchestrator, which imports this package to reach the registries, so a
        # top-level import of a service closes the loop and leaves whichever of the
        # two was imported first half-initialised.
        from app.services.claims import ClaimExtractionService

        return self._own or ClaimExtractionService(settings=self._settings)

    # ----------------------------------------------------------- filing ----

    def _unread(self, kind: ArtifactKind) -> DeskReport:
        missing = (
            "A link was submitted, and fetching the article behind it is not built "
            "yet, so there was no prose to read."
            if kind is ArtifactKind.URL
            else "The submission carried no text to read."
        )
        return DeskReport(
            desk=self.desk,
            verdict=Verdict(
                determination=Determination.INSUFFICIENT,
                headline="No prose to read",
                rationale=f"{missing} Nothing was extracted and nothing was checked.",
                confidence=0.0,
            ),
            ledger=(LedgerEntry("Characters read", "0"),),
        )

    def _submitted(self, text: str) -> DeskReport:
        return DeskReport(
            desk=self.desk,
            verdict=Verdict(
                determination=Determination.REQUIRES_VERIFICATION,
                headline="One claim, as submitted",
                rationale=(
                    "The submission is a single assertion and was taken as written "
                    "rather than extracted from surrounding prose. Whether it holds "
                    "is the fact-check desk's finding, not this one."
                ),
                confidence=0.0,
            ),
            annotations=(
                Annotation(
                    ref=1,
                    quote=text,
                    note="Submitted as a claim; passed on for checking.",
                    determination=Determination.REQUIRES_VERIFICATION,
                ),
            ),
            ledger=(
                LedgerEntry("Characters read", str(len(text))),
                LedgerEntry("Claims found", "1"),
                LedgerEntry("Extraction", "taken as submitted"),
            ),
        )

    def _filed(self, extraction: Extraction) -> DeskReport:
        checkable = extraction.checkable
        aside = tuple(c for c in extraction.claims if not c.checkable)
        return DeskReport(
            desk=self.desk,
            verdict=Verdict(
                determination=(
                    Determination.REQUIRES_VERIFICATION
                    if checkable
                    else Determination.INSUFFICIENT
                ),
                headline=(
                    f"{len(checkable)} checkable claim(s) found"
                    if checkable
                    else "No checkable claim found"
                ),
                rationale=_rationale(extraction),
                # Zero on purpose, in both directions. This desk states what it read;
                # confidence belongs to a finding about the claim, and it has none.
                confidence=0.0,
            ),
            annotations=(
                *(
                    Annotation(
                        ref=claim.ref,
                        quote=claim.quote,
                        note="Identified as a factual claim that requires verification.",
                        determination=Determination.REQUIRES_VERIFICATION,
                    )
                    for claim in checkable
                ),
                *(
                    Annotation(
                        ref=claim.ref,
                        quote=claim.quote,
                        note=_why(claim.reason),
                        determination=Determination.INSUFFICIENT,
                    )
                    for claim in aside
                ),
            ),
            ledger=_ledger(extraction, checkable, aside),
            signals=_signals(extraction, checkable),
        )


def _rationale(extraction: Extraction) -> str:
    checkable = extraction.checkable
    if not checkable:
        return (
            f"{extraction.sentences} sentence(s) were read and none of them makes an "
            "assertion that could be checked against sources. Copy can be entirely "
            "opinion, instruction or narration without anything being wrong with it, "
            "so this is a finding about the writing and not about its truth."
        )
    return (
        f"{len(checkable)} of {len(extraction.claims)} assertion(s) across "
        f"{extraction.sentences} sentence(s) are stated specifically enough to check. "
        "Each is marked and passed to the fact-check desk; what the evidence says "
        "about them is that desk's finding."
    )


def _why(reason: str) -> str:
    return f"Set aside: {reason or 'not a checkable claim'}."


def _ledger(
    extraction: Extraction,
    checkable: tuple[ExtractedClaim, ...],
    aside: tuple[ExtractedClaim, ...],
) -> tuple[LedgerEntry, ...]:
    entries = [
        LedgerEntry("Sentences read", str(extraction.sentences)),
        LedgerEntry("Assertions found", str(len(extraction.claims))),
        LedgerEntry("Claims to check", str(len(checkable))),
        LedgerEntry("Claims set aside", str(len(aside))),
    ]
    return tuple(entries)


def _signals(
    extraction: Extraction, checkable: tuple[ExtractedClaim, ...]
) -> tuple[Signal, ...]:
    found = len(extraction.claims)
    return (
        Signal(
            label="Checkable share",
            reading=f"{len(checkable)} of {found} assertion(s)",
            weight=round(len(checkable) / found, 4) if found else 0.0,
        ),
    )


def _clipped(text: str) -> str:
    return text if len(text) <= LEDGER_QUOTE else f"{text[: LEDGER_QUOTE - 1]}…"


def build(settings: Settings | None = None) -> TextDesk:
    """Factory for the registry, which resolves desks with no arguments."""
    return TextDesk(settings=settings or get_settings())
