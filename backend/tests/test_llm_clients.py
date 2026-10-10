"""The two text-generation clients, against recorded response shapes.

Both ``parse`` methods are public so they can be exercised here without a network, and
the bodies below are the vendor documentation these clients were written from — if a
provider moves a field, the assertion that fails should be the one naming it.

The request bodies are asserted too, which is unusual in this codebase and specific to
these two providers. Getting a request field wrong here does not fail: Ollama accepts a
top-level ``max_tokens`` and ignores it, and answers a streaming request with
newline-delimited JSON rather than an error. Both mistakes surface as a truncated or
unparseable answer several layers away, so what goes out is checked where it is built.

Requests are driven through :class:`httpx.MockTransport`, assigned to the client's
private pool the way :mod:`tests.test_provider_http` documents — the alternative is a
transport parameter on production code whose only caller is a test.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import ConfigurationError, LLMError, ProviderUnavailableError
from app.llm.base import Message
from app.llm.ollama import OllamaClient
from app.llm.openai import MAX_TOKENS_FIELD, OpenAIClient
from app.providers import http as http_module
from app.providers.http import Http

KEY = "sk-secret-key-value-1234"

ASKED = (
    Message(role="system", content="You are the final reasoning step."),
    Message(role="user", content="CLAIM: the rate was held."),
)

#: The head of a reply the reasoning layer would accept, so what these clients hand
#: upward is the shape the layer above actually reads.
ANSWER = '{"verdict": "TRUE", "confidence": 80, "reasoning": "Both agree.", '


@pytest.fixture
def settings() -> Settings:
    """Both endpoints pinned, because pydantic-settings reads ``os.environ``.

    A developer with ``OLLAMA_BASE_URL`` exported at a real GPU box would otherwise
    run a different suite from CI — and one of the tests below asserts a full URL.
    """
    return Settings(
        _env_file=None,
        OPENAI_API_KEY=KEY,
        OPENAI_BASE_URL="https://api.openai.com/v1",
        OLLAMA_BASE_URL="http://localhost:11434",
        LLM_MAX_RETRIES=1,
        LLM_TIMEOUT_SECONDS=5.0,
    )


@pytest.fixture
def slept(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Every backoff the client asked for, without waiting for any of them."""
    calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        calls.append(seconds)

    monkeypatch.setattr(http_module.asyncio, "sleep", fake_sleep)
    return calls


def wire(
    client: Http, handler: Callable[[httpx.Request], httpx.Response]
) -> list[httpx.Request]:
    """Point ``client`` at ``handler`` and return the list it records requests in."""
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client._client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return seen


def answers(
    body: object, status: int = 200
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return handler


def sent(request: httpx.Request) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(request.content)
    return parsed


# --------------------------------------------------------- openai responses ----

OPENAI_BODY: dict[str, Any] = {
    "id": "chatcmpl-B9MHDbslfkBeAs8l4bebGdFOJ6PeG",
    "object": "chat.completion",
    "created": 1741570283,
    # Not the model that was asked for. The API aliases and silently upgrades, and
    # this is the field that makes a stored verdict reproducible.
    "model": "gpt-4o-mini-2024-07-18",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": f'{ANSWER}"evidence": ["E1", "E2"]}}',
                "refusal": None,
                "annotations": [],
            },
            "logprobs": None,
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 1117, "completion_tokens": 46, "total_tokens": 1163},
    "service_tier": "default",
}


def test_openai_reads_the_answer_and_what_produced_it(settings: Settings) -> None:
    answer = OpenAIClient(settings).parse(OPENAI_BODY)

    assert answer.text.startswith('{"verdict": "TRUE"')
    assert answer.model == "gpt-4o-mini-2024-07-18"
    assert answer.prompt_tokens == 1117
    assert answer.completion_tokens == 46
    assert answer.finish_reason == "stop"


def test_openai_falls_back_to_the_configured_model(settings: Settings) -> None:
    """An OpenAI-compatible server need not echo the field, and some do not."""
    body = {**OPENAI_BODY}
    del body["model"]

    assert OpenAIClient(settings).parse(body).model == settings.OPENAI_MODEL


def test_openai_reports_no_counts_rather_than_invented_ones(settings: Settings) -> None:
    body = {**OPENAI_BODY, "usage": {"prompt_tokens": True, "completion_tokens": None}}

    answer = OpenAIClient(settings).parse(body)

    # ``True`` is an int, and a count of 1 read off a flag is worse than no count.
    assert answer.prompt_tokens is None
    assert answer.completion_tokens is None


def test_openai_refuses_a_response_with_no_choices(settings: Settings) -> None:
    with pytest.raises(LLMError, match="no choices") as raised:
        OpenAIClient(settings).parse({"id": "chatcmpl-1", "object": "chat.completion"})

    assert raised.value.details["keys"] == ["id", "object"]


def test_openai_refuses_a_truncated_answer_and_says_why(settings: Settings) -> None:
    """A model stopped at the ceiling can return content that is empty.

    The reason is carried because without it the rejection reads as a model that
    cannot follow instructions rather than a ``max_tokens`` set too low.
    """
    body = {
        **OPENAI_BODY,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": ""},
                "finish_reason": "length",
            }
        ],
    }

    with pytest.raises(LLMError, match="empty completion") as raised:
        OpenAIClient(settings).parse(body)

    assert raised.value.details["finish_reason"] == "length"


def test_openai_refuses_a_filtered_answer(settings: Settings) -> None:
    """A content filter returns null content, which is a failure and not silence."""
    body = {
        **OPENAI_BODY,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": None},
                "finish_reason": "content_filter",
            }
        ],
    }

    with pytest.raises(LLMError, match="empty completion"):
        OpenAIClient(settings).parse(body)


def test_openai_refuses_a_body_that_is_not_an_object(settings: Settings) -> None:
    with pytest.raises(LLMError, match="list where an object"):
        OpenAIClient(settings).parse([OPENAI_BODY])


# --------------------------------------------------------- ollama responses ----

OLLAMA_BODY: dict[str, Any] = {
    "model": "llama3",
    "created_at": "2026-02-14T09:30:11.1234Z",
    "message": {"role": "assistant", "content": f'{ANSWER}"evidence": ["E1"]}}'},
    "done": True,
    "done_reason": "stop",
    "total_duration": 4883583458,
    "prompt_eval_count": 1117,
    "eval_count": 46,
}


def test_ollama_reads_the_answer_and_what_produced_it(settings: Settings) -> None:
    answer = OllamaClient(settings).parse(OLLAMA_BODY)

    assert answer.text.startswith('{"verdict": "TRUE"')
    assert answer.model == "llama3"
    assert answer.prompt_tokens == 1117
    assert answer.completion_tokens == 46
    assert answer.finish_reason == "stop"


def test_ollama_refuses_an_empty_answer_and_says_why(settings: Settings) -> None:
    body = {**OLLAMA_BODY, "message": {"role": "assistant", "content": ""}}

    with pytest.raises(LLMError, match="empty completion") as raised:
        OllamaClient(settings).parse(body)

    assert raised.value.details["done_reason"] == "stop"


def test_ollama_refuses_a_body_with_no_message(settings: Settings) -> None:
    with pytest.raises(LLMError, match="empty completion") as raised:
        OllamaClient(settings).parse({"model": "llama3", "done": True})

    assert raised.value.details["keys"] == ["done", "model"]


def test_ollama_refuses_a_body_that_is_not_an_object(settings: Settings) -> None:
    """A streamed reply decodes line by line, and no line is this shape."""
    with pytest.raises(LLMError, match="str where an object"):
        OllamaClient(settings).parse('{"done": false}')


# ------------------------------------------------------------- what is sent ----


async def test_openai_sends_the_credential_and_the_ceiling(settings: Settings) -> None:
    client = OpenAIClient(settings)
    seen = wire(client, answers(OPENAI_BODY))

    await client.complete(ASKED, temperature=0.0, max_tokens=700)

    request = seen[0]
    assert str(request.url) == "https://api.openai.com/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {KEY}"

    body = sent(request)
    assert body["model"] == settings.OPENAI_MODEL
    assert body["temperature"] == 0.0
    assert body[MAX_TOKENS_FIELD] == 700
    assert body["messages"] == [
        {"role": "system", "content": ASKED[0].content},
        {"role": "user", "content": ASKED[1].content},
    ]


async def test_openai_omits_the_ceiling_when_none_was_asked_for(
    settings: Settings,
) -> None:
    """A provider's own default is not the same thing as a field set to null."""
    client = OpenAIClient(settings)
    seen = wire(client, answers(OPENAI_BODY))

    await client.complete(ASKED)

    assert MAX_TOKENS_FIELD not in sent(seen[0])


async def test_ollama_turns_streaming_off_and_names_the_ceiling_its_way(
    settings: Settings,
) -> None:
    """The two fields that fail silently when they are wrong.

    Left to default, ``/api/chat`` streams and the reply is not a JSON document. Put
    at the top level, ``max_tokens`` is accepted and ignored and the answer comes back
    truncated with no error anywhere.
    """
    client = OllamaClient(settings)
    seen = wire(client, answers(OLLAMA_BODY))

    await client.complete(ASKED, temperature=0.2, max_tokens=700)

    request = seen[0]
    assert str(request.url) == "http://localhost:11434/api/chat"
    assert "authorization" not in request.headers

    body = sent(request)
    assert body["stream"] is False
    assert body["options"] == {"temperature": 0.2, "num_predict": 700}
    assert "max_tokens" not in body


async def test_the_retry_setting_counts_retries_and_not_attempts(
    settings: Settings, slept: list[float]
) -> None:
    """``LLM_MAX_RETRIES=1`` is one retry, so two tries — which is what is passed."""
    client = OllamaClient(settings)
    seen = wire(client, answers({"error": "model is loading"}, status=503))

    with pytest.raises(ProviderUnavailableError):
        await client.complete(ASKED)

    assert len(seen) == settings.LLM_MAX_RETRIES + 1
    assert slept == [0.5]


async def test_a_rejected_key_never_reaches_the_error_it_raises(
    settings: Settings,
) -> None:
    """Provider messages quote the request, and a provider error reaches a client."""
    client = OpenAIClient(settings)
    echoed = {"error": {"message": f"Incorrect API key provided: {KEY}"}}
    wire(client, answers(echoed, status=401))

    with pytest.raises(LLMError) as raised:
        await client.complete(ASKED)

    assert KEY not in str(raised.value)
    assert "***" in str(raised.value)


# ------------------------------------------------------------- construction ----


def test_openai_without_a_key_is_a_configuration_error() -> None:
    """A 500 whose fix is an environment variable — not a 501, and not a 502."""
    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
        OpenAIClient(Settings(_env_file=None, OPENAI_API_KEY=None))


def test_groq_endpoint_uses_its_provider_key_over_shell_openai_key() -> None:
    settings = Settings(
        _env_file=None,
        OPENAI_API_KEY="wrong-shell-key",
        GROQ_API_KEY="groq-key",
        OPENAI_BASE_URL="https://api.groq.com/openai/v1",
    )

    client = OpenAIClient(settings)

    assert client.name == "groq"
    assert client._key == "groq-key"


def test_ollama_without_a_base_url_is_a_configuration_error() -> None:
    """The only thing a credential-free provider can refuse at construction."""
    with pytest.raises(ConfigurationError, match="OLLAMA_BASE_URL"):
        OllamaClient(Settings(_env_file=None, OLLAMA_BASE_URL="   "))


def test_a_base_url_with_a_trailing_slash_builds_one_path(settings: Settings) -> None:
    """Both base URLs are written by hand into an env file, and both forms get typed."""
    openai = settings.model_copy(update={"OPENAI_BASE_URL": "https://vllm.test/v1/"})
    ollama = settings.model_copy(update={"OLLAMA_BASE_URL": "http://gpu.test:11434/"})

    assert OpenAIClient(openai).url == "https://vllm.test/v1/chat/completions"
    assert OllamaClient(ollama).url == "http://gpu.test:11434/api/chat"
