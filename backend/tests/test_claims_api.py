"""The claim extraction endpoint.

Driven against a stub extractor rather than spaCy. That is not only about speed: it
is the assertion that ``app.nlp`` keeps every heavy import inside a function body, so
the endpoint, its schemas and their adapters can be exercised on a machine with no
NLP libraries installed. If that discipline ever slips, these tests are what fail —
at import, loudly, rather than in production on a container that shipped without a
model.

The ordering assertions matter more than they look. A client needs to know whether
its request was well formed, so validation and the size ceiling both have to run
before anything touches the extractor.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError
from tests.stubs import SAMPLE_TEXT, StubClaimExtractor, extractor_bench

V1 = "/api/v1"


@pytest.fixture
def tiny_limit(app: FastAPI, settings: Settings) -> Settings:
    """Shrink MAX_TEXT_CHARS so the size guard can be tripped with a short string."""
    small = settings.model_copy(update={"MAX_TEXT_CHARS": 20})
    app.dependency_overrides[get_settings] = lambda: small
    return small


async def test_extraction_returns_the_claims(client: AsyncClient) -> None:
    stub = StubClaimExtractor()

    with extractor_bench(stub):
        response = await client.post(f"{V1}/extract-claim", json={"text": SAMPLE_TEXT})

    assert response.status_code == 200
    body = response.json()
    assert [claim["ref"] for claim in body["claims"]] == [1, 2]
    assert body["claims"][0]["text"] == "The bridge opened in March 2026."
    assert stub.seen == [SAMPLE_TEXT]


async def test_the_text_reaches_the_extractor_unmodified(client: AsyncClient) -> None:
    """No trimming, no normalising. Offsets in the response index what was sent."""
    stub = StubClaimExtractor()
    text = f"  {SAMPLE_TEXT}\n\n"

    with extractor_bench(stub):
        await client.post(f"{V1}/extract-claim", json={"text": text})

    assert stub.seen == [text]


async def test_both_counts_are_reported(client: AsyncClient) -> None:
    """`count` is every claim; `checkable_count` is the ones a desk could act on.

    One number for both is the bug this exists to prevent: a UI saying "2 claims
    found" over a list containing one opinion.
    """
    with extractor_bench(StubClaimExtractor()):
        response = await client.post(f"{V1}/extract-claim", json={"text": SAMPLE_TEXT})

    body = response.json()
    assert body["count"] == 2
    assert body["checkable_count"] == 1
    assert body["sentences"] == 2


async def test_an_unfit_claim_is_returned_with_its_reason(client: AsyncClient) -> None:
    """Marked, not dropped. "Skipped" and "judged opinion" are different answers."""
    with extractor_bench(StubClaimExtractor()):
        response = await client.post(f"{V1}/extract-claim", json={"text": SAMPLE_TEXT})

    unfit = response.json()["claims"][1]
    assert unfit["checkable"] is False
    assert unfit["reason"] == "opinion"


async def test_offsets_locate_the_quote_in_the_submitted_text(
    client: AsyncClient,
) -> None:
    """The invariant the whole offset discipline exists for."""
    with extractor_bench(StubClaimExtractor()):
        response = await client.post(f"{V1}/extract-claim", json={"text": SAMPLE_TEXT})

    for claim in response.json()["claims"]:
        assert SAMPLE_TEXT[claim["start"] : claim["end"]] == claim["quote"]


async def test_entity_offsets_locate_the_entity(client: AsyncClient) -> None:
    with extractor_bench(StubClaimExtractor()):
        response = await client.post(f"{V1}/extract-claim", json={"text": SAMPLE_TEXT})

    body = response.json()
    for entity in body["entities"] + body["claims"][0]["entities"]:
        assert SAMPLE_TEXT[entity["start"] : entity["end"]] == entity["text"]
        assert entity["label"] == "DATE"


async def test_keywords_are_normalised_and_ordered(client: AsyncClient) -> None:
    with extractor_bench(StubClaimExtractor()):
        response = await client.post(f"{V1}/extract-claim", json={"text": SAMPLE_TEXT})

    keywords = response.json()["keywords"]
    assert [k["term"] for k in keywords] == ["bridge", "march"]
    assert keywords[0]["score"] == 1.0
    assert all(0 < k["score"] <= 1 for k in keywords)


async def test_a_missing_model_is_a_500_naming_the_fix(client: AsyncClient) -> None:
    """The single most common way to deploy this broken, so the message is the fix."""
    stub = StubClaimExtractor(
        raises=ConfigurationError(
            "The spaCy model 'en_core_web_sm' is not installed.",
            details={"install": "python -m spacy download en_core_web_sm"},
        )
    )

    with extractor_bench(stub):
        response = await client.post(f"{V1}/extract-claim", json={"text": "x y z w"})

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "configuration_error"
    assert error["details"]["install"] == "python -m spacy download en_core_web_sm"


async def test_errors_use_the_error_envelope(client: AsyncClient) -> None:
    response = await client.post(f"{V1}/extract-claim", json={"text": ""})

    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


async def test_empty_text_is_refused_before_the_extractor(client: AsyncClient) -> None:
    stub = StubClaimExtractor()

    with extractor_bench(stub):
        response = await client.post(f"{V1}/extract-claim", json={"text": ""})

    assert response.status_code == 422
    assert stub.seen == []


async def test_missing_text_is_refused(client: AsyncClient) -> None:
    response = await client.post(f"{V1}/extract-claim", json={})

    assert response.status_code == 422


async def test_an_unexpected_field_is_refused(client: AsyncClient) -> None:
    response = await client.post(
        f"{V1}/extract-claim", json={"text": "x", "language": "en"}
    )

    assert response.status_code == 422


async def test_oversized_text_is_413_and_never_reaches_the_extractor(
    client: AsyncClient, tiny_limit: Settings
) -> None:
    """The guard runs first, so an oversized body does not load a 12 MB model."""
    stub = StubClaimExtractor()

    with extractor_bench(stub):
        response = await client.post(f"{V1}/extract-claim", json={"text": "x" * 50})

    assert response.status_code == 413
    assert response.json()["error"]["details"] == {
        "field": "text",
        "characters": 50,
        "limit": 20,
    }
    assert stub.seen == []
