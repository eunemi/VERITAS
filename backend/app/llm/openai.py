"""GPT, through the ``/chat/completions`` request shape.

``OPENAI_BASE_URL`` is configurable because that shape is no longer OpenAI's alone —
vLLM, llama.cpp's server, LM Studio and several hosted vendors all speak it — so
pointing this at one of them is a setting rather than a second client.

Two response fields are read that a caller might not expect to matter. ``model`` is
recorded rather than assumed: the API aliases and silently upgrades, so
``gpt-4o-mini`` in the request can be a dated snapshot in the reply, and it is the
reply that makes a stored verdict reproducible. ``finish_reason`` is carried because
``"length"`` means the JSON :mod:`app.reasoning` asked for is truncated — the answer
is then rejected, which is right, but without the reason the rejection looks like a
model that cannot follow instructions rather than a ceiling set too low.

Structured tasks from ``app.llm.structured`` request JSON mode through their system
instruction. The resulting body is still validated against its schema; JSON mode
alone does not validate citations or a model's interpretation of the evidence.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

from app.core.config import Settings
from app.core.errors import ConfigurationError, LLMError
from app.llm.base import Completion, Message
from app.providers.http import Http

__all__ = ["MAX_TOKENS_FIELD", "OpenAIClient", "build"]

#: Which field carries the output ceiling.
#:
#: Two exist and neither works everywhere. ``max_tokens`` is the long-standing field
#: and the one every OpenAI-compatible server implements; OpenAI's own reference
#: marks it deprecated in favour of ``max_completion_tokens``, which its reasoning
#: models require and older third-party servers reject. This is the compatible
#: choice, named here because a deployment on a reasoning model has to change it and
#: should not have to find it.
MAX_TOKENS_FIELD = "max_tokens"


class OpenAIClient(Http):
    """Generates text through OpenAI's chat completions endpoint."""

    name = "openai"
    # Background verifications can wait for a model's per-minute token window.
    max_backoff_seconds = 60.0
    error = LLMError

    def __init__(self, settings: Settings) -> None:
        if urlsplit(settings.OPENAI_BASE_URL).hostname == "api.groq.com":
            self.name = "groq"
        key = settings.chat_api_key()
        if key is None:
            raise ConfigurationError(
                "GROQ_API_KEY is not set" if self.name == "groq" else "OPENAI_API_KEY is not set",
                details={"provider": self.name},
            )
        self._key = key.get_secret_value()
        super().__init__(
            timeout=settings.LLM_TIMEOUT_SECONDS,
            # Attempts, not retries: the setting counts retries, so a configured 2
            # means three tries in total.
            attempts=settings.LLM_MAX_RETRIES + 1,
            secrets=(self._key,),
        )
        self._model = settings.OPENAI_MODEL
        self.url = f"{settings.OPENAI_BASE_URL.rstrip('/')}/chat/completions"

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> Completion:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            body[MAX_TOKENS_FIELD] = max_tokens
        # Structured tasks should not depend on stripping prose or markdown fences.
        if messages and "Return JSON only" in messages[0].content:
            body["response_format"] = {"type": "json_object"}
        payload = await self.fetch(
            "POST",
            self.url,
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        return self.parse(payload)

    def parse(self, payload: Any) -> Completion:
        """Turn a decoded response body into a :class:`Completion`.

        Public so a test can exercise it against a recorded body without a network,
        which is the only way the reading in here is verifiable at all.

        Empty content raises rather than returning an empty completion. A content
        filter and a truncation both produce one, both are failures, and a caller
        handed ``text=""`` would report the model as having said nothing.
        """
        if not isinstance(payload, dict):
            raise LLMError(
                f"{self.name} returned {type(payload).__name__} where an object "
                "was expected",
                provider=self.name,
            )
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMError(
                f"{self.name} response carries no choices",
                provider=self.name,
                details={"keys": sorted(k for k in payload if isinstance(k, str))},
            )
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        reason = _text(first.get("finish_reason"))
        if not isinstance(content, str) or not content.strip():
            raise LLMError(
                f"{self.name} returned an empty completion",
                provider=self.name,
                details={"finish_reason": reason},
            )

        usage = payload.get("usage")
        return Completion(
            text=content,
            model=_text(payload.get("model")) or self._model,
            prompt_tokens=_count(usage, "prompt_tokens"),
            completion_tokens=_count(usage, "completion_tokens"),
            finish_reason=reason or None,
        )


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _count(usage: Any, key: str) -> int | None:
    """One token count, or ``None`` when the provider did not report it.

    ``bool`` is excluded because it is an ``int`` subclass, and ``True`` arriving
    here would become a token count of 1 invented from a field that was not one.
    """
    if not isinstance(usage, dict):
        return None
    value = usage.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def build(settings: Settings) -> OpenAIClient:
    """Factory for the client registry in :mod:`app.llm`."""
    return OpenAIClient(settings)
