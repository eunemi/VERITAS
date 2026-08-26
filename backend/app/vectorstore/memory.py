"""An in-process vector store, and the thing that keeps the seam a seam.

Two reasons to have it, and the first is not testing. A deployment that wants
relevance ranking without operating a database gets it here: the arithmetic below
is the arithmetic Chroma performs, and at the sizes one claim produces — tens of
passages, not millions — a linear scan is not the slow option.

The second is that :mod:`app.vectorstore.chroma` cannot be reviewed for
replaceability on its own. A protocol with one implementation behind it is a
protocol shaped like that implementation. ``tests/test_vectorstore.py`` runs one
contract against both, so a Chroma assumption that leaked into the interface
fails here rather than in the review of whatever replaces it.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from app.core.errors import VectorStoreError
from app.vectorstore.base import Document, Match

if TYPE_CHECKING:
    from app.core.config import Settings


class InMemoryVectorStore:
    """Vectors in a dict, searched by cosine similarity.

    Not shared between processes, which is the one thing to know before choosing
    it: two uvicorn workers each hold their own index, so a passage written while
    serving one request may be absent from the next.
    """

    name = "memory"

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, tuple[Document, tuple[float, ...]]]] = {}
        # Upsert reads the collection's existing width before writing to it, so
        # two concurrent writes of differently-sized vectors must not interleave.
        self._lock = asyncio.Lock()

    async def upsert(
        self,
        collection: str,
        documents: Sequence[Document],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        if len(documents) != len(vectors):
            raise VectorStoreError(
                f"{len(documents)} document(s) were passed with {len(vectors)} "
                f"vector(s); they are paired positionally.",
                provider=self.name,
            )
        if not documents:
            return

        widths = {len(vector) for vector in vectors}
        if len(widths) > 1:
            raise VectorStoreError(
                f"vectors of differing widths were passed: {sorted(widths)}",
                provider=self.name,
            )
        async with self._lock:
            held = self._collections.setdefault(collection, {})
            # A width that changes under an existing collection means the embedder
            # was swapped without reindexing. Every stored vector is now
            # incomparable with every new one, and refusing is the only reading of
            # that which does not silently return nonsense rankings.
            established = {len(vector) for _, vector in held.values()}
            if established and widths != established:
                raise VectorStoreError(
                    f"collection {collection!r} holds {established.pop()}-dimension "
                    f"vectors and was passed {widths.pop()}-dimension ones; reindex "
                    f"it after changing embedding model.",
                    provider=self.name,
                )
            for document, vector in zip(documents, vectors, strict=True):
                held[document.id] = (document, tuple(float(value) for value in vector))

    async def query(
        self,
        collection: str,
        vector: Sequence[float],
        *,
        top_k: int = 5,
    ) -> list[Match]:
        if top_k <= 0:
            return []
        probe = tuple(float(value) for value in vector)
        async with self._lock:
            held = list(self._collections.get(collection, {}).values())
        if not held:
            return []
        if len(held[0][1]) != len(probe):
            raise VectorStoreError(
                f"collection {collection!r} holds {len(held[0][1])}-dimension "
                f"vectors and was queried with a {len(probe)}-dimension one.",
                provider=self.name,
            )

        found = [
            Match(
                id=document.id,
                text=document.text,
                score=_cosine(probe, stored),
                metadata=dict(document.metadata),
            )
            for document, stored in held
        ]
        # Ties broken on the id rather than left to insertion order: equal scores
        # are common once two passages share their vocabulary, and a caller taking
        # the first must not get a different one per process.
        found.sort(key=lambda match: (-match.score, match.id))
        return found[:top_k]

    async def delete(self, collection: str, ids: Sequence[str]) -> None:
        async with self._lock:
            held = self._collections.get(collection)
            if held is None:
                return
            for id_ in ids:
                held.pop(id_, None)

    async def aclose(self) -> None:
        return None

    def stored(self, collection: str) -> Mapping[str, Any]:
        """Every document in ``collection``, keyed by id.

        Off the protocol on purpose. Nothing in the application reads it; it is
        how a test inspects what was written without a query deciding which
        documents it gets to see.
        """
        held = self._collections.get(collection, {})
        return {id_: document for id_, (document, _) in held.items()}


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Similarity in ``[-1, 1]``, higher being closer.

    The same number Chroma reports as ``1 - distance`` under its cosine space,
    which is what lets one contract test assert on both stores' scores.
    """
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    scale = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / scale if scale else 0.0


def build(settings: Settings) -> InMemoryVectorStore:
    """Factory for the registry in :mod:`app.vectorstore`."""
    return InMemoryVectorStore()
