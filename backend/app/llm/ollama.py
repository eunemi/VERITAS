"""Llama 3 through a local Ollama server.

No credential — the base URL is the whole configuration — so an absent
``OLLAMA_BASE_URL`` is the only thing this can refuse at construction. A server that
is not running surfaces later, as a
:class:`~app.core.errors.ProviderUnavailableError` from the connection attempt, which
is the same shape every other provider's outage takes.

``stream`` is sent as ``False`` on purpose: ``/api/chat`` streams by default and
answers a streaming request with newline-delimited JSON objects, one per token, which
is not a JSON document and would fail to decode. Whether the reply is one object or a
hundred is decided by that flag, not by how the response is read.

Generation parameters live under ``options``, and ``num_predict`` is Ollama's spelling
of a token ceiling. The mapping matters more than it looks: passing ``max_tokens`` at
the top level is silently accepted and silently ignored, so a bad translation here
produces a truncated answer with no error anywhere.

Like :mod:`app.llm.openai` this does not use the provider's JSON mode
(``"format": "json"``). The reasoning layer validates every field against a closed
table regardless, so the two clients stay interchangeable on the seam they share.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.core.config import Settings
from app.core.errors import ConfigurationError, LLMError
from app.llm.base import Completion, Message
from app.providers.http import Http

__all__ = ["OllamaClient", "build"]


class OllamaClient(Http):
    """Generates text through Ollama's ``/api/chat`` endpoint."""

    name = "ollama"
    error = LLMError

    def __init__(self, settings: Settings) -> None:
        base = settings.OLLAMA_BASE_URL.strip()
        if not base:
            raise ConfigurationError(
                "OLLAMA_BASE_URL is not set", details={"provider": self.name}
            )
        super().__init__(
            timeout=settings.LLM_TIMEOUT_SECONDS,
            attempts=settings.LLM_MAX_RETRIES + 1,
        )
        self._model = settings.OLLAMA_MODEL
        self.url = f"{base.rstrip('/')}/api/chat"

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> Completion:
        options: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        payload = await self.fetch(
            "POST",
            self.url,
            headers={"Content-Type": "application/json"},
            json={
                "model": self._model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "stream": False,
                "options": options,
            },
        )
        return self.parse(payload)

    def parse(self, payload: Any) -> Completion:
        """Turn a decoded response body into a :class:`Completion`.

        Public for the same reason as :meth:`app.llm.openai.OpenAIClient.parse`: a
        recorded body is the only way to check this reading without a server.
        """
        if not isinstance(payload, dict):
            raise LLMError(
                f"{self.name} returned {type(payload).__name__} where an object "
                "was expected",
                provider=self.name,
            )
        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        reason = _text(payload.get("done_reason"))
        if not isinstance(content, str) or not content.strip():
            raise LLMError(
                f"{self.name} returned an empty completion",
                provider=self.name,
                details={
                    "done_reason": reason,
                    "keys": sorted(k for k in payload if isinstance(k, str)),
                },
            )

        return Completion(
            text=content,
            model=_text(payload.get("model")) or self._model,
            prompt_tokens=_count(payload.get("prompt_eval_count")),
            completion_tokens=_count(payload.get("eval_count")),
            finish_reason=reason or None,
        )


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _count(value: Any) -> int | None:
    """A token count, or ``None`` when the field was absent or not a number.

    ``bool`` is rejected because it is an ``int`` subclass and would otherwise turn a
    flag into a count of one.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def build(settings: Settings) -> OllamaClient:
    """Factory for the client registry in :mod:`app.llm`."""
    return OllamaClient(settings)
