"""The vector store seam.

Which store is used is decided by ``VECTOR_STORE_PROVIDER``. Two are registered
here and neither is favoured by the code above them: :mod:`app.vectorstore.chroma`
persists to disk, :mod:`app.vectorstore.memory` holds the index in the process.
FAISS remains a setting with nothing behind it, so selecting it raises
:class:`~app.core.errors.NotImplementedYetError` rather than falling back — a
deployment that asked for one store must not silently get another.

Having two is the point rather than a convenience. One contract in
``tests/test_vectorstore.py`` runs against both, which is the difference between a
replaceable database and a protocol that happens to describe Chroma.
"""

from __future__ import annotations

from app.core.config import Settings, VectorStoreProvider
from app.core.registry import ProviderRegistry
from app.vectorstore.base import Document, Match, VectorStore
from app.vectorstore.chroma import ChromaVectorStore
from app.vectorstore.chroma import build as _build_chroma
from app.vectorstore.memory import InMemoryVectorStore
from app.vectorstore.memory import build as _build_memory

#: Vector stores, keyed by provider.
vector_stores: ProviderRegistry[VectorStoreProvider, VectorStore] = ProviderRegistry(
    "vector store"
)

vector_stores.register(VectorStoreProvider.CHROMA, _build_chroma)
vector_stores.register(VectorStoreProvider.MEMORY, _build_memory)


def get_vector_store(settings: Settings) -> VectorStore:
    """Return the configured vector store."""
    return vector_stores.resolve(settings.VECTOR_STORE_PROVIDER, settings)


__all__ = [
    "ChromaVectorStore",
    "Document",
    "InMemoryVectorStore",
    "Match",
    "VectorStore",
    "get_vector_store",
    "vector_stores",
]
