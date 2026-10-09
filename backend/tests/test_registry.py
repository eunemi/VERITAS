"""The provider seams.

Some are implemented and some are deliberately not, and the two failure modes must
stay distinguishable. A seam with nothing behind it raises
:class:`~app.core.errors.NotImplementedYetError` — a 501, "nobody has built this" —
and a seam that is built but has no key raises
:class:`~app.core.errors.ConfigurationError`, a 500 whose fix is a variable in the
environment. Reporting one as the other sends whoever hits it to the wrong place.

The rest of the file is about substitution: registries are module-level, and the
pattern for supplying a fake instead of calling a paid API is
:func:`fake_llm_registered` below.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

import pytest

from app.audio import transcribers
from app.core.config import (
    FactCheckProvider,
    LLMProvider,
    SearchProvider,
    Settings,
    SpeechProvider,
    VectorStoreProvider,
    VisionProvider,
)
from app.core.errors import ConfigurationError, NotImplementedYetError
from app.core.registry import ProviderRegistry
from app.factcheck import fact_check_clients, get_fact_check_client
from app.llm import (
    Completion,
    LLMClient,
    Message,
    embedders,
    get_embedder,
    get_llm_client,
    llm_clients,
)
from app.llm.openai import build as build_openai
from app.search import get_search_client, search_clients
from app.vectorstore import get_vector_store, vector_stores
from app.vectorstore.base import VectorStore
from app.vision import detectors, readers


@pytest.fixture
def settings() -> Settings:
    """Local settings holding no provider keys, whatever the machine's environment has.

    The keys are passed as ``None`` rather than left to their defaults because
    pydantic-settings reads ``os.environ`` even with ``_env_file`` disabled, and a
    developer with a real ``TAVILY_API_KEY`` exported would otherwise run a
    different suite from CI.
    """
    return Settings(
        _env_file=None,
        ENVIRONMENT="local",
        TAVILY_API_KEY=None,
        GOOGLE_FACT_CHECK_API_KEY=None,
        OPENAI_API_KEY=None,
    )


# ----------------------------------------------------------- the registry ----


def test_resolving_an_unregistered_provider_names_the_seam() -> None:
    registry: ProviderRegistry[str, object] = ProviderRegistry("widget")

    with pytest.raises(NotImplementedYetError) as raised:
        registry.resolve("brass")

    assert raised.value.details == {"seam": "widget", "requested": "brass"}
    assert "widget" in raised.value.message


def test_not_implemented_is_a_501_not_a_500() -> None:
    """ "Not built yet" must never be reported to a client as "broken"."""
    registry: ProviderRegistry[str, object] = ProviderRegistry("widget")

    with pytest.raises(NotImplementedYetError) as raised:
        registry.resolve("brass")

    assert raised.value.status == 501
    assert raised.value.code == "not_implemented"


def test_a_registered_factory_receives_the_arguments() -> None:
    registry: ProviderRegistry[str, dict[str, object]] = ProviderRegistry("widget")
    registry.register("brass", lambda *args, **kwargs: {"args": args, "kwargs": kwargs})

    built = registry.resolve("brass", 1, flag=True)

    assert built == {"args": (1,), "kwargs": {"flag": True}}


def test_registering_over_a_key_replaces_it() -> None:
    """This is how a test substitutes a fake for a real provider."""
    registry: ProviderRegistry[str, str] = ProviderRegistry("widget")
    registry.register("brass", lambda: "real")
    registry.register("brass", lambda: "fake")

    assert registry.resolve("brass") == "fake"


def test_registered_reports_what_is_available() -> None:
    registry: ProviderRegistry[str, str] = ProviderRegistry("widget")
    registry.register("brass", lambda: "b")
    registry.register("steel", lambda: "s")

    assert set(registry.registered()) == {"brass", "steel"}

    registry.unregister("brass")
    assert registry.registered() == ("steel",)


def test_unregistering_an_absent_key_is_not_an_error() -> None:
    registry: ProviderRegistry[str, str] = ProviderRegistry("widget")

    registry.unregister("never-there")


# ------------------------------------------------------------- the seams -----


def test_a_seam_with_nothing_behind_it_is_not_implemented(settings: Settings) -> None:
    """Guards against a half-wired provider: registered here, unusable there."""
    faiss = settings.model_copy(
        update={"VECTOR_STORE_PROVIDER": VectorStoreProvider.FAISS}
    )
    # OpenAI is registered as a text-generation client and not as an embedder, so
    # selecting it for embedding names a real provider through a seam it does not
    # implement. ``EMBEDDING_PROVIDER`` defaults to ``hashing`` precisely so this is
    # a deployment that opted in, not the shape every deployment starts in.
    openai_embeddings = settings.model_copy(
        update={"EMBEDDING_PROVIDER": LLMProvider.OPENAI}
    )

    with pytest.raises(NotImplementedYetError):
        get_embedder(openai_embeddings)

    with pytest.raises(NotImplementedYetError):
        get_vector_store(faiss)


def test_a_seam_missing_its_key_is_a_configuration_error(settings: Settings) -> None:
    """Built, but this deployment cannot use it — which is a different problem.

    All three of these providers exist and work; what is absent is a credential. A
    caller told "not implemented" would go looking for unwritten code, so the two
    failures are separate types and this is the test that keeps them apart.
    """
    for resolve in (get_search_client, get_fact_check_client, get_llm_client):
        with pytest.raises(ConfigurationError):
            resolve(settings)


def test_the_local_model_resolves_with_no_key(settings: Settings) -> None:
    """Llama 3 through Ollama needs a URL and not a credential.

    Which is why the key check lives in each client rather than in the registry: the
    two text-generation providers behind one seam do not agree about what configuring
    them means, and a shared check would have to invent a requirement for one of them.
    """
    ollama = settings.model_copy(update={"LLM_PROVIDER": LLMProvider.OLLAMA})

    client = get_llm_client(ollama)

    assert isinstance(client, LLMClient)
    assert client.name == "ollama"


def test_the_in_process_store_resolves_with_no_key_and_no_dependency(
    settings: Settings,
) -> None:
    """A supported configuration rather than a test double.

    It is also what makes the vector-store seam demonstrably replaceable — two
    implementations against one contract, in :mod:`tests.test_vectorstore` — and
    resolving it here is what proves the registration is reachable from the setting.
    """
    memory = settings.model_copy(
        update={"VECTOR_STORE_PROVIDER": VectorStoreProvider.MEMORY}
    )

    store = get_vector_store(memory)

    assert isinstance(store, VectorStore)
    assert store.name == "memory"


def test_embedding_and_completion_are_separate_seams(settings: Settings) -> None:
    """``hashing`` implements one and not the other, which is why there are two.

    One registry keyed by :class:`~app.core.config.LLMProvider` would make selecting
    an embedder that needs no key imply a text-generation client that does not exist.
    So the two settings are set to the same value here and read by different seams:
    ``get_embedder`` answers from ``EMBEDDING_PROVIDER`` and ``get_llm_client`` from
    ``LLM_PROVIDER``, and only the first of them can be served.
    """
    hashing = settings.model_copy(
        update={
            "EMBEDDING_PROVIDER": LLMProvider.HASHING,
            "LLM_PROVIDER": LLMProvider.HASHING,
        }
    )

    assert get_embedder(hashing).name == "hashing"

    with pytest.raises(NotImplementedYetError):
        get_llm_client(hashing)


def test_the_embedder_ignores_the_completion_provider(settings: Settings) -> None:
    """The default deployment: generate with OpenAI, embed locally.

    This is the pairing the two settings exist for. Keyed on one enum member, an
    OpenAI deployment could not embed at all, which would make retrieval unreachable
    everywhere the default is left alone.
    """
    default = settings.model_copy(update={"LLM_PROVIDER": LLMProvider.OPENAI})

    assert default.EMBEDDING_PROVIDER is LLMProvider.HASHING
    assert get_embedder(default).name == "hashing"


def test_the_seams_account_for_every_configurable_provider() -> None:
    """A provider that can be selected but never registered is a dead setting.

    Not "everything is registered": FAISS is deliberately unbuilt, and ``hashing``
    embeds without generating. Asserting the split as exact sets is what makes adding
    an enum member without an implementation a decision recorded here rather than one
    that slipped in.
    """
    assert set(LLMProvider) == {
        LLMProvider.OPENAI,
        LLMProvider.OLLAMA,
        LLMProvider.HASHING,
    }
    assert set(VectorStoreProvider) == {
        VectorStoreProvider.CHROMA,
        VectorStoreProvider.FAISS,
        VectorStoreProvider.MEMORY,
    }
    assert set(FactCheckProvider) == {FactCheckProvider.GOOGLE}
    assert set(VisionProvider) == {VisionProvider.TESSERACT, VisionProvider.YOLO}
    assert set(SpeechProvider) == {SpeechProvider.WHISPER}

    assert set(llm_clients.registered()) == {LLMProvider.OPENAI, LLMProvider.OLLAMA}
    assert set(embedders.registered()) == {LLMProvider.HASHING}
    assert set(search_clients.registered()) == set(SearchProvider)
    assert set(fact_check_clients.registered()) == set(FactCheckProvider)
    assert set(vector_stores.registered()) == {
        VectorStoreProvider.CHROMA,
        VectorStoreProvider.MEMORY,
    }
    # One enum, two roles, and neither registry holds the other's key: reading text
    # and finding objects are separate jobs, and a deployment that wants only the
    # first should not be selecting a detector to get it.
    assert set(readers.registered()) == {VisionProvider.TESSERACT}
    assert set(detectors.registered()) == {VisionProvider.YOLO}
    assert set(transcribers.registered()) == {SpeechProvider.WHISPER}


class FakeLLM:
    """Satisfies :class:`app.llm.base.LLMClient` without leaving the process."""

    name = "fake"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> Completion:
        return Completion(text=messages[-1].content.upper(), model="fake-1")

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_llm_registered() -> Iterator[None]:
    """A fake in OpenAI's place, with the real factory put back afterwards.

    Restored rather than unregistered, because OpenAI is a real registration now and
    dropping it would leave the seam emptier than the application ships it — a later
    test asserting what is registered would then fail on this fixture's leftovers
    rather than on its own subject.
    """
    llm_clients.register(LLMProvider.OPENAI, FakeLLM)
    try:
        yield
    finally:
        # Registries are module-level, so a leaked registration would make a
        # later test pass for the wrong reason.
        llm_clients.register(LLMProvider.OPENAI, build_openai)


@pytest.mark.usefixtures("fake_llm_registered")
async def test_a_substituted_provider_is_what_callers_get(
    settings: Settings,
) -> None:
    client = get_llm_client(settings)

    assert isinstance(client, LLMClient)
    assert client.name == "fake"
    # The factory is handed the settings object, which is what lets a real
    # provider read its own key and timeouts without a second lookup.
    assert client.settings is settings  # type: ignore[attr-defined]

    answer = await client.complete([Message(role="user", content="hello")])
    assert answer.text == "HELLO"


@pytest.mark.usefixtures("fake_llm_registered")
def test_substituting_one_provider_does_not_answer_for_the_others(
    settings: Settings,
) -> None:
    """A fake registered over OpenAI must not be what ``ollama`` resolves to."""
    ollama = settings.model_copy(update={"LLM_PROVIDER": LLMProvider.OLLAMA})

    assert get_llm_client(ollama).name == "ollama"
