"""Reads the artifact and settles what is going to be checked."""

from __future__ import annotations

from app.core.config import Settings
from app.domain import Artifact, ArtifactKind, ExtractedClaim, SkippedClaim
from app.graph.state import AgentNote, GraphState
from app.research import queries
from app.services.claims import ClaimExtractionService

NAME = "claim"


class ClaimAgent:
    """Turns an artifact into numbered claims and the queries to search for them."""

    def __init__(
        self, *, settings: Settings, extractor: ClaimExtractionService
    ) -> None:
        self._settings = settings
        self._extractor = extractor

    async def __call__(self, state: GraphState) -> GraphState:
        artifact = state["artifact"]
        found, skipped = await self._read(artifact)

        ceiling = self._settings.SEARCH_MAX_CLAIMS
        kept, over = found[:ceiling], found[ceiling:]
        skipped += tuple(
            SkippedClaim(
                claim=claim.text,
                reason=(
                    f"only the first {ceiling} claims of {len(found)} were "
                    f"researched (SEARCH_MAX_CLAIMS={ceiling})"
                ),
            )
            for claim in over
        )

        return GraphState(
            claims=kept,
            queries=tuple(
                queries.build(c, limit=self._settings.SEARCH_QUERIES_PER_CLAIM)
                for c in kept
            ),
            skipped=skipped,
            trace=(
                AgentNote(
                    NAME,
                    f"{len(kept)} claim(s) to check, {len(skipped)} set aside",
                ),
            ),
        )

    async def _read(
        self, artifact: Artifact
    ) -> tuple[tuple[ExtractedClaim, ...], tuple[SkippedClaim, ...]]:
        if artifact.kind is ArtifactKind.CLAIM and artifact.content:
            return (_verbatim(artifact.content),), ()
        if artifact.kind is ArtifactKind.TEXT and artifact.content:
            return await self._extract(artifact.content)
        # No prose to read — a URL or media artifact that nothing has fetched. The
        # judge reports UNCERTAIN off an empty claim list rather than this agent
        # inventing a claim to check.
        return (), ()

    async def _extract(
        self, text: str
    ) -> tuple[tuple[ExtractedClaim, ...], tuple[SkippedClaim, ...]]:
        extraction = await self._extractor.extract(text)
        return (
            tuple(c for c in extraction.claims if c.checkable),
            tuple(
                SkippedClaim(claim=c.text, reason=c.reason or "not a checkable claim")
                for c in extraction.claims
                if not c.checkable
            ),
        )


def _verbatim(content: str) -> ExtractedClaim:
    """A caller's claim as its own extraction, spanning all of what they sent.

    ``quote`` is the same string as ``text`` because nothing was read out of
    anything — which keeps the ``text[start:end] == quote`` invariant true instead of
    filling the offsets with something that breaks it.
    """
    claim = content.strip()
    return ExtractedClaim(ref=1, text=claim, quote=claim, start=0, end=len(claim))
