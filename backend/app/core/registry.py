"""A tiny provider registry.

Most seams in this application have to be swappable — the LLM (completion and
embedding separately, because one provider implements only the second), web search,
the fact-check database, the vector store, claim extraction, the image reader and
the object detector. They all need the same three operations: register an
implementation under a key, resolve the key the settings name, and fail clearly
when that key has no implementation behind it.

This is that, once, generically, rather than one copy of the same dictionary lookup
per seam. Implementations register themselves; nothing here imports a provider, so
adding one does not touch this file and the registry has no opinion about what it
holds.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

from app.core.errors import NotImplementedYetError

#: The enum member identifying a provider (e.g. ``LLMProvider.OPENAI``).
K = TypeVar("K")
#: The client type the seam produces (e.g. ``LLMClient``).
V = TypeVar("V")

#: Factories take the settings object and return a ready client. Passing settings
#: rather than unpacked keyword arguments keeps every provider's constructor
#: signature identical, which is what makes them interchangeable.
Factory = Callable[..., V]


class ProviderRegistry(Generic[K, V]):
    """Maps provider keys to the factories that build them.

    ``seam`` names what is being registered and appears in error messages, which
    is the difference between "unknown provider: faiss" and a message that says
    which of the four seams was misconfigured.
    """

    def __init__(self, seam: str) -> None:
        self.seam = seam
        self._factories: dict[K, Factory[V]] = {}

    def register(self, key: K, factory: Factory[V]) -> None:
        """Bind ``key`` to ``factory``, replacing any previous binding.

        Replacement is allowed on purpose: a test substitutes a fake provider by
        registering over the real one, and refusing would mean the test needs a
        private attribute instead.
        """
        self._factories[key] = factory

    def unregister(self, key: K) -> None:
        """Remove ``key`` if present. Used by tests to undo a substitution."""
        self._factories.pop(key, None)

    def registered(self) -> tuple[K, ...]:
        """Return the keys that currently have implementations."""
        return tuple(self._factories)

    def factory(self, key: K) -> Factory[V] | None:
        """The factory bound to ``key``, or ``None`` if nothing is.

        For a test that has to put back what it displaced. :meth:`unregister` is
        enough only for a seam that started out empty; substituting over a real
        registration and then unregistering leaves the seam emptier than it was
        found, and every later resolve in the process becomes a 501.
        """
        return self._factories.get(key)

    def resolve(self, key: K, *args: object, **kwargs: object) -> V:
        """Build the provider bound to ``key``.

        Raises :class:`NotImplementedYetError` when the key is a valid provider
        the application knows about but nothing has been registered for — the
        state every seam is in while this foundation has no implementations
        behind it — and :class:`ConfigurationError` when the key is not one this
        seam recognises at all.
        """
        factory = self._factories.get(key)
        if factory is None:
            known = ", ".join(sorted(str(k) for k in self._factories)) or "none"
            raise NotImplementedYetError(
                f"No {self.seam} provider is registered for {key!r}. "
                f"Registered: {known}.",
                details={"seam": self.seam, "requested": str(key)},
            )
        return factory(*args, **kwargs)
