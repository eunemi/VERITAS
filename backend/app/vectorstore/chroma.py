"""ChromaDB behind the :class:`~app.vectorstore.base.VectorStore` protocol.

Four things here are decisions rather than plumbing.

**The import is inside the constructor.** ``chromadb`` carries a large dependency
tree, and :mod:`app.vectorstore` is imported by the service layer whichever
provider is configured, so importing at module scope would make a deployment
running on :mod:`app.vectorstore.memory` install a database it never opens. Same
rule, for the same reason, as :mod:`app.nlp.resources` — and a missing install is
a :class:`~app.core.errors.ConfigurationError` naming the command that fixes it,
not an ``ImportError`` from four frames down.

**Every call crosses a thread.** Chroma's client is synchronous and does real
file I/O; calling it from a coroutine would stall the event loop for every other
request the worker is serving.

**Distance becomes similarity.** Chroma reports cosine *distance*, where smaller
is closer, and :class:`~app.vectorstore.base.Match` publishes similarity, where
larger is. ``1 - distance`` is that conversion, and it is exactly the number
:func:`app.vectorstore.memory._cosine` computes directly — which is what lets one
contract test cover both stores.

**Metadata is flattened to scalars.** Chroma stores ``str``, ``int``, ``float``
and ``bool`` and nothing else. Encoding a passage's carriers into that is
:mod:`app.vectorstore.evidence`'s job, since it is the module that knows what a
carrier is; all this does is drop keys whose value is ``None``, because an absent
value and a missing key are the same statement and Chroma can only store one of
them.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

import anyio.to_thread

from app.core.errors import ConfigurationError, VectorStoreError
from app.vectorstore.base import Document, Match

if TYPE_CHECKING:
    from app.core.config import Settings

#: One operation against an already-resolved collection handle.
Work = Callable[[Any], Any]

#: The vector space every collection is created in. Cosine rather than the L2
#: default: embeddings are compared by direction, and two passages of very
#: different lengths about the same fact are close in angle and far in distance.
SPACE = "cosine"


class ChromaVectorStore:
    """A persistent Chroma collection per ``collection`` name."""

    name = "chroma"

    def __init__(self, persist_directory: str) -> None:
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - depends on the install
            raise ConfigurationError(
                "chromadb is not installed, and VECTOR_STORE_PROVIDER=chroma "
                "requires it. Install it with `pip install chromadb`, or select "
                "the in-process store with VECTOR_STORE_PROVIDER=memory."
            ) from exc

        self._client = chromadb.PersistentClient(path=persist_directory)

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

        encoded = [_scalars(document.metadata) for document in documents]
        # A list of empty dicts is rejected, so a document carrying no metadata
        # gets ``None`` rather than ``{}``.
        metadatas = [entry or None for entry in encoded] if any(encoded) else None
        await self._run(
            "upsert",
            collection,
            lambda handle: handle.upsert(
                ids=[document.id for document in documents],
                documents=[document.text for document in documents],
                embeddings=[list(vector) for vector in vectors],
                metadatas=metadatas,
            ),
        )

    async def query(
        self,
        collection: str,
        vector: Sequence[float],
        *,
        top_k: int = 5,
    ) -> list[Match]:
        if top_k <= 0:
            return []
        answer = await self._run(
            "query",
            collection,
            lambda handle: handle.query(
                query_embeddings=[list(vector)],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            ),
        )
        return _matches(answer)

    async def delete(self, collection: str, ids: Sequence[str]) -> None:
        if not ids:
            return
        await self._run(
            "delete", collection, lambda handle: handle.delete(ids=list(ids))
        )

    async def aclose(self) -> None:
        """Nothing to release: ``PersistentClient`` writes through on every call."""
        return None

    async def _run(self, operation: str, collection: str, work: Work) -> Any:
        """Run one collection operation off the event loop.

        The collection handle is fetched inside the worker thread too, because
        ``get_or_create_collection`` is itself a synchronous round trip to disk.
        """

        def call() -> Any:
            handle = self._client.get_or_create_collection(
                name=collection, metadata={"hnsw:space": SPACE}
            )
            return work(handle)

        try:
            return await anyio.to_thread.run_sync(call)
        except Exception as exc:
            # Every vendor exception becomes VectorStoreError. Chroma's own
            # exception types are not part of the protocol, and a caller that
            # learned to catch them would be coupled to the store this seam exists
            # to make replaceable.
            raise VectorStoreError(
                f"chroma {operation} on collection {collection!r} failed: {exc}",
                provider=self.name,
                details={"collection": collection, "operation": operation},
            ) from exc


def _matches(answer: Mapping[str, Any]) -> list[Match]:
    """One query's results, in the protocol's shape.

    Chroma answers a batch of query vectors, so every field arrives wrapped in a
    list of one. ``metadatas`` and ``distances`` can each be ``None`` when nothing
    matched, which is why every lookup below is defensive rather than indexed.
    """
    ids = (answer.get("ids") or [[]])[0]
    texts = (answer.get("documents") or [[]])[0] or [""] * len(ids)
    metadatas = (answer.get("metadatas") or [[]])[0] or [None] * len(ids)
    distances = (answer.get("distances") or [[]])[0] or [0.0] * len(ids)
    return [
        Match(
            id=id_,
            text=text or "",
            score=1.0 - float(distance),
            metadata=dict(metadata or {}),
        )
        for id_, text, metadata, distance in zip(
            ids, texts, metadatas, distances, strict=False
        )
    ]


def _scalars(metadata: Mapping[str, Any]) -> dict[str, str | int | float | bool]:
    """``metadata`` reduced to what Chroma can hold.

    Raises rather than coercing anything else: a list quietly stored as its
    ``repr`` would come back out as a string that looks like a list, and the
    in-process store would have returned the list — a difference between two
    implementations of one protocol, which is the failure this package is
    arranged to prevent.
    """
    kept: dict[str, str | int | float | bool] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, str | int | float | bool):
            kept[key] = value
            continue
        raise VectorStoreError(
            f"metadata key {key!r} holds {type(value).__name__}; chroma stores "
            f"str, int, float and bool only.",
            provider="chroma",
        )
    return kept


def build(settings: Settings) -> ChromaVectorStore:
    """Factory for the registry in :mod:`app.vectorstore`."""
    return ChromaVectorStore(settings.CHROMA_PERSIST_DIRECTORY)
