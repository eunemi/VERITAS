"""The evidence index: store a dossier's passages, retrieve a claim's.

Sits on two seams and belongs to neither. :mod:`app.llm` turns text into vectors,
:mod:`app.vectorstore` stores and searches them, and
:mod:`app.vectorstore.evidence` decides what a passage's identity and metadata are;
this coordinates the three and is the only place that knows the order.

Nothing here reorders, drops or rescores a dossier. Retrieval is a second way of
reading what was already gathered — :mod:`app.research.evidence` selects passages
by lexical overlap with the claim, and this selects them by vector distance, which
finds the ones that restate the claim rather than repeat its words. A caller wants
both, which is why this returns its own type and does not edit a
:class:`~app.domain.research.ClaimResearch`.

**Retrieval is per claim, structurally.** Each claim's passages live in their own
collection, so a query cannot reach another claim's — see
:mod:`app.vectorstore.evidence` for why that is a naming decision rather than a
filtering one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from app.core.logging import get_logger
from app.domain.research import ClaimResearch
from app.llm import get_embedder
from app.llm.base import Embedder
from app.vectorstore import evidence as passages
from app.vectorstore import get_vector_store
from app.vectorstore.base import VectorStore

logger = get_logger(__name__)

if TYPE_CHECKING:
    from app.core.config import Settings

__all__ = ["EvidenceIndex", "build"]

#: How many extra results to ask the store for, as a multiple of the caller's
#: ``top_k``. Duplicates are collapsed *after* the store has ranked, so asking for
#: exactly ``top_k`` would return fewer than ``top_k`` distinct passages whenever
#: any of them were truncation variants of each other.
OVERFETCH = 3


class EvidenceIndex:
    """Stores the passages of a dossier and retrieves the ones a claim asks for.

    Takes its two collaborators rather than the settings object. Both are seams,
    resolved once by :func:`build`, and passing them in is what lets the retrieval
    path be exercised against a store that never leaves the process.
    """

    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder,
        *,
        top_k: int = 8,
        min_similarity: float = 0.0,
        namespace: str = "",
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._top_k = top_k
        self._min_similarity = min_similarity
        self._collections: set[str] = set()
        self._namespace = namespace

    def _collection(self, claim: str) -> str:
        value = f"{self._namespace}:{claim}" if self._namespace else claim
        return passages.collection_for(value)

    async def index(self, research: ClaimResearch) -> int:
        """Store ``research``'s passages, returning how many distinct ones were written.

        The count is below the number of passages in the dossier whenever two
        sources carried the same sentence, which is the index-time deduplication
        working. Idempotent: a second call with the same dossier overwrites the same
        ids rather than adding to them.
        """
        documents = passages.documents(research)
        if not documents:
            return 0
        vectors = await self._embedder.embed([document.text for document in documents])
        collection = self._collection(research.claim)
        await self._store.upsert(collection, documents, vectors)
        self._collections.add(collection)
        return len(documents)

    async def relevant(
        self, claim: str, *, top_k: int | None = None
    ) -> tuple[passages.Relevant, ...]:
        """The stored passages nearest ``claim``, closest first, duplicates collapsed.

        Empty when nothing was indexed for the claim, and empty when everything
        indexed for it sits below ``min_similarity`` — a vector store answers every
        query with its nearest neighbours however distant they are, so the floor is
        what stops an index of three unrelated passages reporting its least
        unrelated one as evidence.
        """
        limit = self._top_k if top_k is None else top_k
        if limit <= 0:
            return ()
        probe = await self._embedder.embed([claim])
        found = await self._store.query(
            self._collection(claim), probe[0], top_k=limit * OVERFETCH
        )
        near = [
            passages.decode(match)
            for match in found
            if match.score >= self._min_similarity
        ]
        return tuple(passages.collapse(near)[:limit])

    async def aclose(self) -> None:
        await self._store.aclose()
        await self._embedder.aclose()

    async def discard(self) -> None:
        """Delete collections created for one transient examination.

        The fact-check desk uses the index only to reorder the dossier that is
        already in memory. Keeping Chroma collections after that read would turn
        every unique claim into permanent on-disk state and eventually increase
        both disk and index RSS without improving a later examination.
        """
        for collection in tuple(self._collections):
            try:
                await self._store.delete_collection(collection)
            except Exception:
                # The examination result is already available; cleanup must not
                # turn a successful verification into a failed one. The store's
                # own error contains the provider and collection for diagnostics.
                logger.warning(
                    "temporary evidence collection cleanup failed",
                    extra={"collection": collection},
                )
                continue
        self._collections.clear()
        await self.aclose()


def build(settings: Settings) -> EvidenceIndex:
    """The index the configuration asks for.

    Resolves both seams here rather than lazily, so a deployment that has selected
    a store it cannot open finds out when it wires the service up and not on the
    first claim it tries to check.
    """
    return EvidenceIndex(
        get_vector_store(settings),
        get_embedder(settings),
        top_k=settings.EVIDENCE_TOP_K,
        min_similarity=settings.EVIDENCE_MIN_SIMILARITY,
        # A transient run must never delete another run's collection for the same
        # claim when both use the process-wide Chroma persistence directory.
        namespace=uuid4().hex,
    )
