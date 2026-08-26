"""The contract every vector store implements."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class Document:
    """Something to index.

    The vector is passed alongside rather than held here: embedding is the LLM
    seam's job, and a store that took raw text would have to know how to embed it,
    which would tie the two seams together.
    """

    id: str
    text: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Match:
    """A nearest-neighbour hit.

    ``score`` is similarity — higher is closer — normalised by the
    implementation, because Chroma reports a distance and FAISS reports an inner
    product, and a caller comparing raw numbers across the two would be wrong.
    """

    id: str
    text: str
    score: float
    metadata: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class VectorStore(Protocol):
    """Stores and retrieves vectors.

    Implementations raise :class:`app.core.errors.VectorStoreError` on failure.
    Metadata filtering is deliberately absent: no caller needs it yet, and
    inventing the filter language before there is a query to serve would fix it
    in the shape of whichever store was implemented first.
    """

    name: str

    async def upsert(
        self,
        collection: str,
        documents: Sequence[Document],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        """Insert or replace ``documents``, positionally paired with ``vectors``."""
        ...

    async def query(
        self,
        collection: str,
        vector: Sequence[float],
        *,
        top_k: int = 5,
    ) -> list[Match]:
        """Return the ``top_k`` nearest documents, closest first."""
        ...

    async def delete(self, collection: str, ids: Sequence[str]) -> None:
        """Remove ``ids``. Missing ids are not an error."""
        ...

    async def aclose(self) -> None:
        """Flush anything buffered and release resources."""
        ...
