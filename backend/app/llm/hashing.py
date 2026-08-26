"""A deterministic embedder with no model behind it.

Feature hashing. Every content word of a text is hashed into one of
``dimensions`` buckets and the bucket is incremented or decremented — the digest's
low bit picks the sign — and the vector is then L2-normalised so cosine similarity
is a dot product. The signed variant is used because unsigned collisions all push
one way and accumulate, which is what makes two unrelated texts look related.

**This measures shared vocabulary, not meaning.** Two passages reporting the same
fact in different words score near nought here; a real embedding model is what
fixes that, and swapping to one is a change to ``LLM_PROVIDER``. It is registered
as a provider rather than hidden in a test because the alternative is an evidence
index that cannot run at all without a paid API key: with this, the retrieval path
is exercisable offline and reproducibly, and a deployment that has no key gets
ranking that is at least honest about what it is.

``blake2b`` rather than :func:`hash`, which is salted per process — two workers
would put the same word in different buckets, and a vector written by one would be
meaningless to the other. Same reason as :mod:`app.research.dedupe`.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.core.errors import ConfigurationError
from app.research import terms

if TYPE_CHECKING:
    from app.core.config import Settings


class HashingEmbedder:
    """Embeds by hashing words into buckets."""

    name = "hashing"

    def __init__(self, dimensions: int) -> None:
        if dimensions < 1:
            raise ConfigurationError(
                f"EMBEDDING_DIMENSIONS is {dimensions}; it must be at least 1."
            )
        self.dimensions = dimensions

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.vector(text) for text in texts]

    def vector(self, text: str) -> list[float]:
        """``text`` as one unit vector, or the zero vector if it has no content words.

        Zero rather than an arbitrary direction: a text of nothing but stopwords is
        similar to nothing, and every cosine against it is 0.0, which is the
        truthful answer rather than a rank it did not earn.
        """
        buckets = [0.0] * self.dimensions
        for word in terms.content_words(text):
            digest = hashlib.blake2b(word.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            buckets[bucket] += -1.0 if digest[-1] & 1 else 1.0
        norm = math.sqrt(sum(value * value for value in buckets))
        return [value / norm for value in buckets] if norm else buckets

    async def aclose(self) -> None:
        return None


def build(settings: Settings) -> HashingEmbedder:
    """Factory for the embedder registry in :mod:`app.llm`."""
    return HashingEmbedder(settings.EMBEDDING_DIMENSIONS)
