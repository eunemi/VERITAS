"""Evidence grounding and image intake regressions, with no network dependencies."""

import io
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.core.config import Settings
from app.core.errors import ConfigurationError
from app.domain import Artifact, ArtifactKind, Determination, ImageDetail, LedgerEntry
from app.graph.agents import semantic
from app.graph.agents.semantic import Answer, Citation, SemanticJudge
from app.graph.state import cases
from app.graph.verdict import Judgement
from app.repositories.sql.coding import dump_detail, load_detail
from app.schemas.verification import MediaArtifactIn
from app.vision import context
from tests.graph_bench import state
from tests.research_bench import source


def gathered(*, same_domain=False, syndicated=False):
    sources = (
        source(
            "https://nasa.gov/mission",
            ref=1,
            snippet="The lander reached the Moon, not Mars.",
            cluster=1,
        ),
        source(
            "https://nasa.gov/other" if same_domain else "https://isro.gov.in/mission",
            ref=2,
            snippet="Chandrayaan-3 touched down on the lunar surface.",
            cluster=1 if syndicated else 2,
        ),
    )
    return state(sources, text="Chandrayaan-3 landed on Mars.", grade=False)


def answer(**changes):
    return Answer(
        verdict="REFUTED",
        confidence=0.93,
        explanation="Both sources describe a lunar landing.",
        citations=[
            Citation(ref=1, passage=0, stance="refutes"),
            Citation(ref=2, passage=0, stance="refutes"),
        ],
    ).model_copy(update=changes)


async def test_refutation_uses_actual_retrieved_quotes(monkeypatch):
    monkeypatch.setattr(semantic, "ask", AsyncMock(return_value=answer()))
    result = await SemanticJudge(Settings(_env_file=None))(gathered())
    assert result["ruling"].judgement is Judgement.REFUTED
    assert (
        result["ruling"].claims[0].indications[0].quote
        == "The lander reached the Moon, not Mars."
    )


@pytest.mark.parametrize("changes", [{"same_domain": True}, {"syndicated": True}])
async def test_reprints_cannot_manufacture_corroboration(monkeypatch, changes):
    monkeypatch.setattr(semantic, "ask", AsyncMock(return_value=answer()))
    result = await SemanticJudge(Settings(_env_file=None))(gathered(**changes))
    assert result["ruling"].judgement is Judgement.UNCERTAIN


async def test_hallucinated_citation_is_not_a_verdict(monkeypatch):
    monkeypatch.setattr(
        semantic,
        "ask",
        AsyncMock(
            return_value=answer(
                citations=[Citation(ref=999, passage=0, stance="refutes")]
            )
        ),
    )
    result = await SemanticJudge(Settings(_env_file=None))(gathered())
    assert result["ruling"].judgement is Judgement.UNCERTAIN


async def test_model_outage_does_not_turn_word_overlap_into_truth(monkeypatch):
    monkeypatch.setattr(
        semantic, "ask", AsyncMock(side_effect=ConfigurationError("model unavailable"))
    )
    result = await SemanticJudge(Settings(_env_file=None))(gathered())
    assert result["ruling"].judgement is Judgement.UNCERTAIN
    assert result["ruling"].confidence == 0


async def test_no_sources_never_calls_the_model(monkeypatch):
    call = AsyncMock()
    monkeypatch.setattr(semantic, "ask", call)
    result = await SemanticJudge(Settings(_env_file=None)).rule(
        replace(cases(gathered())[0], research=None), "2026-10-10"
    )
    assert result.judgement is Judgement.UNCERTAIN
    call.assert_not_called()


def test_image_caption_and_details_survive_the_contract():
    artifact = MediaArtifactIn(
        kind="image", url="https://example.com/a.jpg", content="Delhi today"
    ).to_domain()
    assert artifact.content == "Delhi today"
    detail = ImageDetail(
        width=80,
        height=40,
        text="news",
        description="A news card",
        observations=("A headline",),
        metadata=(LedgerEntry("Format", "PNG"),),
        web_status="searched",
    )
    assert load_detail(dump_detail(detail)) == detail


async def test_missing_reverse_key_is_not_an_empty_success():
    with pytest.raises(ConfigurationError):
        await context.reverse_matches(
            context.Prepared(b"", 1, 1, ()), Settings(_env_file=None)
        )


def test_empty_environment_keys_are_not_configured_providers():
    settings = Settings(_env_file=None, GOOGLE_VISION_API_KEY="", OPENAI_API_KEY=" ")
    assert settings.GOOGLE_VISION_API_KEY is None
    assert settings.OPENAI_API_KEY is None


async def test_reverse_results_only_link_actual_provider_pages(monkeypatch):
    fetch = AsyncMock(
        return_value={
            "responses": [
                {
                    "webDetection": {
                        "pagesWithMatchingImages": [
                            {
                                "url": "https://news.example/photo",
                                "pageTitle": "Photo report",
                                "fullMatchingImages": [
                                    {"url": "https://news.example/photo.jpg"}
                                ],
                            },
                            {"url": "javascript:alert(1)", "pageTitle": "bad"},
                        ]
                    }
                }
            ]
        }
    )
    monkeypatch.setattr(context.Http, "fetch", fetch)
    matches = await context.reverse_matches(
        context.Prepared(b"pixels", 1, 1, ()),
        Settings(_env_file=None, GOOGLE_VISION_API_KEY="test-key"),
    )
    assert len(matches) == 1
    assert matches[0].url == "https://news.example/photo"
    assert matches[0].determination is Determination.REQUIRES_VERIFICATION
    assert "Full image match" in matches[0].extract


async def test_image_upload_validates_pixels_and_can_be_read_locally(
    client, settings, tmp_path
):
    from app.desks.image import ImageDesk

    settings.UPLOAD_DIRECTORY = str(tmp_path)
    invalid = await client.post(
        "/api/v1/files/upload-media",
        files={"file": ("fake.png", b"not an image", "image/png")},
    )
    assert invalid.status_code == 422
    buffer = io.BytesIO()
    Image.new("RGB", (80, 40), "white").save(buffer, "PNG")
    uploaded = await client.post(
        "/api/v1/files/upload-media",
        files={"file": ("image.png", buffer.getvalue(), "image/png")},
    )
    assert uploaded.status_code == 201
    data = await ImageDesk(settings=settings)._fetch(
        Artifact(kind=ArtifactKind.IMAGE, url=uploaded.json()["url"])
    )
    assert data == buffer.getvalue()
