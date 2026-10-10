"""The claim extraction service.

Two things to test and no parser needed for either: the size guard runs before the
extractor is resolved, and the extractor is resolved per call rather than captured at
construction. The second is the one that would go unnoticed — a service that looked
up its extractor in ``__init__`` would work identically until the day a test or a
deployment substituted one, and then quietly keep using the old object.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.errors import LLMError, PayloadTooLargeError
from app.domain import Extraction
from app.services.claims import ClaimExtractionService
from tests.stubs import SAMPLE_TEXT, StubClaimExtractor, extractor_bench


@pytest.fixture
def service(settings: Settings) -> ClaimExtractionService:
    return ClaimExtractionService(settings=settings)


async def test_it_returns_what_the_extractor_found(
    service: ClaimExtractionService,
) -> None:
    stub = StubClaimExtractor()

    with extractor_bench(stub):
        extraction = await service.extract(SAMPLE_TEXT)

    assert extraction.sentences == 2
    assert len(extraction.claims) == 2
    assert len(extraction.checkable) == 1
    assert stub.seen == [SAMPLE_TEXT]


async def test_oversized_text_is_refused_before_the_extractor_is_resolved(
    settings: Settings,
) -> None:
    """The guard is the whole point of the ordering: no model load to reject a body."""
    service = ClaimExtractionService(
        settings=settings.model_copy(update={"MAX_TEXT_CHARS": 10})
    )
    stub = StubClaimExtractor()

    with extractor_bench(stub), pytest.raises(PayloadTooLargeError) as caught:
        await service.extract("x" * 11)

    assert caught.value.details == {"field": "text", "characters": 11, "limit": 10}
    assert stub.seen == []


async def test_the_extractor_is_resolved_per_call(
    service: ClaimExtractionService,
) -> None:
    """A substitution made after the service was built still takes effect.

    Constructed once, then called under two different benches. A service that cached
    its extractor would send both calls to the first stub and this would fail on the
    second assertion.
    """
    first, second = StubClaimExtractor(), StubClaimExtractor()

    with extractor_bench(first):
        await service.extract("The bridge opened in March.")
    with extractor_bench(second):
        await service.extract("The tunnel opened in April.")

    assert first.seen == ["The bridge opened in March."]
    assert second.seen == ["The tunnel opened in April."]


async def test_whitespace_only_text_is_not_an_error(
    service: ClaimExtractionService,
) -> None:
    """Difficult text is a 200. Only a broken extractor is an exception.

    The service does not second-guess the extractor about what is worth reading — it
    passes the string through, and deciding that whitespace yields nothing is the
    extractor's call. :mod:`tests.test_nlp_pipeline` asserts it makes that call.
    """
    stub = StubClaimExtractor()

    with extractor_bench(stub):
        await service.extract("   ")

    assert stub.seen == ["   "]


async def test_a_failed_llm_extractor_falls_back_to_the_local_extractor(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An expired provider key must not prevent live evidence from being gathered."""
    configured = settings.model_copy(
        update={"CLAIM_EXTRACTION_LLM": True, "OPENAI_API_KEY": "provider-key"}
    )
    service = ClaimExtractionService(settings=configured)
    fallback = StubClaimExtractor()

    async def failed(*args: object, **kwargs: object) -> Extraction:
        raise LLMError("provider rejected the key", provider="openai")

    from app.nlp import llm

    monkeypatch.setattr(llm, "extract", failed)
    with extractor_bench(fallback):
        result = await service.extract(SAMPLE_TEXT)

    assert result.sentences == 2
    assert fallback.seen == [SAMPLE_TEXT]
