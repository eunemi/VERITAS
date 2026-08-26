"""The contract every LLM provider implements.

Two capabilities, kept apart because providers do not always offer both and a
caller rarely wants both: text completion and embedding. A component that only
embeds should not have to hold something that can also generate prose.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

#: Who a message is from. No "tool" role yet — nothing here calls tools.
Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class Message:
    """One turn of a conversation."""

    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class Completion:
    """A provider's answer.

    ``model`` is the model that actually served the request, which is not always
    the one that was asked for — providers alias and silently upgrade. Recording
    the real one is what makes a stored verdict reproducible.
    """

    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None


@runtime_checkable
class LLMClient(Protocol):
    """Generates text.

    Implementations raise :class:`app.core.errors.LLMError` (or a subclass) on
    failure, never a provider-specific exception: the point of the seam is that
    callers above it do not learn which vendor is behind it.
    """

    #: Provider name, for logs and error details.
    name: str

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> Completion:
        """Answer ``messages``.

        ``temperature`` defaults to 0: this application's callers want the most
        reproducible answer available, and anything that wants variety asks.
        """
        ...

    async def aclose(self) -> None:
        """Release the underlying connection pool."""
        ...


@runtime_checkable
class Embedder(Protocol):
    """Turns text into vectors, for the vector store to index."""

    name: str

    #: Length of the vectors produced. The vector store needs this at index
    #: creation time, before it has seen a single embedding.
    dimensions: int

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed every string in ``texts``, preserving order."""
        ...

    async def aclose(self) -> None:
        """Release the underlying connection pool."""
        ...
