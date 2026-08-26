"""The LLM seam.

Which provider serves a request is decided by ``LLM_PROVIDER`` and resolved here.
No caller names a vendor; they call :func:`get_llm_client`.

Two text-generation providers are registered: :mod:`app.llm.openai` for GPT and
:mod:`app.llm.ollama` for a local Llama 3. Both are the same two methods behind the
same protocol, and :mod:`app.reasoning` — the only caller that generates text — is
written against the protocol, so which one runs is a deployment's choice and not a
code path.

Neither is imported for its own sake. Both modules are imported here so their
``register`` calls run, which is what makes ``LLM_PROVIDER`` reach an implementation.

One embedder is registered: :mod:`app.llm.hashing`, which needs no key and no
network. It exists so the evidence index in :mod:`app.services.evidence` can be
run and tested without a paid API, and its docstring is explicit that what it
measures is shared vocabulary rather than meaning. It is also the default for
``EMBEDDING_PROVIDER``, which is a separate setting from ``LLM_PROVIDER`` for
exactly the reason the two registries are separate — a deployment generating text
with OpenAI has not thereby configured anything that embeds.
"""

from __future__ import annotations

from app.core.config import LLMProvider, Settings
from app.core.registry import ProviderRegistry
from app.llm.base import Completion, Embedder, LLMClient, Message, Role
from app.llm.hashing import HashingEmbedder
from app.llm.hashing import build as _build_hashing
from app.llm.ollama import OllamaClient
from app.llm.ollama import build as _build_ollama
from app.llm.openai import OpenAIClient
from app.llm.openai import build as _build_openai

#: Text generation, keyed by provider.
llm_clients: ProviderRegistry[LLMProvider, LLMClient] = ProviderRegistry("LLM")

#: Embeddings, keyed by the same provider enum. Separate registry because a
#: provider may implement one and not the other.
embedders: ProviderRegistry[LLMProvider, Embedder] = ProviderRegistry("embedding")

llm_clients.register(LLMProvider.OPENAI, _build_openai)
llm_clients.register(LLMProvider.OLLAMA, _build_ollama)
embedders.register(LLMProvider.HASHING, _build_hashing)


def get_llm_client(settings: Settings) -> LLMClient:
    """Return the configured text-generation client."""
    return llm_clients.resolve(settings.LLM_PROVIDER, settings)


def get_embedder(settings: Settings) -> Embedder:
    """Return the configured embedding client.

    Keyed on ``EMBEDDING_PROVIDER`` rather than ``LLM_PROVIDER``: the two registries
    are separate because the capabilities are, and resolving both from one key would
    mean a deployment could not generate text with OpenAI and embed locally.
    """
    return embedders.resolve(settings.EMBEDDING_PROVIDER, settings)


__all__ = [
    "Completion",
    "Embedder",
    "HashingEmbedder",
    "LLMClient",
    "Message",
    "OllamaClient",
    "OpenAIClient",
    "Role",
    "embedders",
    "get_embedder",
    "get_llm_client",
    "llm_clients",
]
