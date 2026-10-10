"""The verification endpoints, end to end through the real service and store.

These tests go through the HTTP surface rather than calling the service directly,
because what is being checked is the wiring: that a validated body reaches the
service, that a domain rejection becomes the right status with its details intact,
and that the background task actually advances the record.

``ASGITransport`` awaits the full ASGI call, which includes Starlette's background
tasks. So by the time a ``POST /verify`` response is in hand the examination has
already run to whatever conclusion it reaches — which makes submit-then-poll
testable in-process, with no sleeping and no polling loop.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError
from app.domain import ADJUDICATOR, Artifact, ArtifactKind, Desk, Verification
from tests.stubs import (
    StubAdjudicator,
    StubExaminer,
    canned,
    desk_bench,
    furnished,
)

V1 = "/api/v1"


def text_body(content: str = "The minister said the bridge opened in March.", **extra):
    """A minimal valid submission, plus whatever a test wants to add or change."""
    return {"artifact": {"kind": "text", "content": content}, **extra}


@pytest.fixture
def tiny_limit(app: FastAPI, settings: Settings) -> Settings:
    """Shrink MAX_TEXT_CHARS so the size guard can be tripped with a short string."""
    small = settings.model_copy(update={"MAX_TEXT_CHARS": 20})
    app.dependency_overrides[get_settings] = lambda: small
    return small


# ------------------------------------------------------------------ submit ---


async def test_submit_returns_202_with_location(client: AsyncClient) -> None:
    response = await client.post(f"{V1}/verify", json=text_body())

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["id"]
    assert response.headers["location"] == f"{V1}/verification/{body['id']}"


async def test_submit_carries_the_request_id(client: AsyncClient) -> None:
    response = await client.post(f"{V1}/verify", json=text_body())

    assert response.headers["X-Request-ID"]


async def test_text_opens_the_text_and_fact_check_desks(client: AsyncClient) -> None:
    """The roster is derived from the artifact's kind, adjudicator appended."""
    response = await client.post(f"{V1}/verify", json=text_body())

    assert response.json()["desks"] == ["text", "fact-check", "decision"]


async def test_a_narrower_roster_can_be_requested(client: AsyncClient) -> None:
    response = await client.post(f"{V1}/verify", json=text_body(desks=["fact-check"]))

    assert response.json()["desks"] == ["fact-check", "decision"]


async def test_roster_order_does_not_change_the_record(client: AsyncClient) -> None:
    """Two spellings of one roster produce the same record.

    Without normalisation the reports would come back in whichever order the caller
    happened to list the desks, and two identical submissions would differ.
    """
    first = await client.post(
        f"{V1}/verify", json=text_body(desks=["text", "fact-check"])
    )
    second = await client.post(
        f"{V1}/verify", json=text_body(desks=["fact-check", "text"])
    )

    assert first.json()["desks"] == second.json()["desks"]
    assert first.json()["desks"] == ["text", "fact-check", "decision"]


async def test_a_repeated_desk_is_not_opened_twice(client: AsyncClient) -> None:
    response = await client.post(f"{V1}/verify", json=text_body(desks=["text", "text"]))

    assert response.json()["desks"] == ["text", "decision"]


async def test_a_submitted_url_is_echoed_back_unchanged(client: AsyncClient) -> None:
    """No trailing slash, no re-encoding: the caller's own string comes back.

    This is the reason the domain holds a ``str`` rather than a pydantic ``Url``.
    ``HttpUrl`` normalises, and what it normalises has changed across pydantic patch
    releases, so echoing the parsed form would make this response depend on the
    installed version.
    """
    url = "https://example.com"
    submitted = await client.post(
        f"{V1}/verify", json={"artifact": {"kind": "url", "url": url}}
    )
    record = await client.get(f"{V1}/verification/{submitted.json()['id']}")

    assert record.json()["artifact"]["url"] == url


# -------------------------------------------------------------- rejections ---


async def test_a_desk_that_cannot_read_the_kind_is_refused(client: AsyncClient) -> None:
    response = await client.post(f"{V1}/verify", json=text_body(desks=["image"]))

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    # The details are the point: a client learns what it may ask for instead of
    # having to guess from prose.
    assert error["details"] == {
        "desk": "image",
        "artifact_kind": "text",
        "allowed_desks": ["text", "fact-check"],
    }


async def test_the_decision_desk_cannot_be_requested(client: AsyncClient) -> None:
    """It reads the other desks' records; it is never one of the examiners."""
    response = await client.post(f"{V1}/verify", json=text_body(desks=["decision"]))

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["details"]["desk"] == "decision"
    assert "automatically" in error["message"]


async def test_an_empty_roster_is_refused(client: AsyncClient) -> None:
    response = await client.post(f"{V1}/verify", json=text_body(desks=[]))

    assert response.status_code == 422


async def test_an_unknown_desk_is_refused(client: AsyncClient) -> None:
    response = await client.post(f"{V1}/verify", json=text_body(desks=["sports"]))

    assert response.status_code == 422


async def test_empty_content_is_refused(client: AsyncClient) -> None:
    response = await client.post(f"{V1}/verify", json=text_body(content=""))

    assert response.status_code == 422


async def test_an_unknown_artifact_kind_is_refused(client: AsyncClient) -> None:
    response = await client.post(
        f"{V1}/verify", json={"artifact": {"kind": "spreadsheet", "content": "x"}}
    )

    assert response.status_code == 422


async def test_a_field_from_the_wrong_member_is_refused(client: AsyncClient) -> None:
    """`extra="forbid"` is what makes the discriminated union strict rather than
    merely selective: a text artifact carrying a `url` is a mistake worth naming."""
    response = await client.post(
        f"{V1}/verify",
        json={"artifact": {"kind": "text", "content": "x", "url": "https://a.test"}},
    )

    assert response.status_code == 422


async def test_a_malformed_url_is_refused(client: AsyncClient) -> None:
    response = await client.post(
        f"{V1}/verify", json={"artifact": {"kind": "url", "url": "not-a-url"}}
    )

    assert response.status_code == 422


async def test_validation_errors_use_the_error_envelope(client: AsyncClient) -> None:
    """Not FastAPI's default `{"detail": [...]}` — every non-2xx has one shape."""
    response = await client.post(f"{V1}/verify", json={})

    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details", "request_id"}
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


async def test_text_over_the_limit_is_413(
    client: AsyncClient, tiny_limit: Settings
) -> None:
    """A size ceiling is not a schema violation, so it is not a 422."""
    response = await client.post(f"{V1}/verify", json=text_body("x" * 50))

    assert response.status_code == 413
    error = response.json()["error"]
    assert error["code"] == "payload_too_large"
    assert error["details"] == {
        "field": "artifact.content",
        "characters": 50,
        "limit": 20,
    }


# ---------------------------------------------------------------- read back ---


async def test_a_pending_record_reads_back_whole(
    app: FastAPI, client: AsyncClient
) -> None:
    """Written straight to the store, so no background task advances it."""
    record = Verification.submitted(
        artifact=Artifact(kind=ArtifactKind.TEXT, content="copy"),
        desks=(Desk.TEXT,),
    )
    await app.state.verification_repository.create(record)

    response = await client.get(f"{V1}/verification/{record.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["terminal"] is False
    assert body["reports"] == []
    assert body["failure"] is None
    assert body["completed_at"] is None
    assert [d["desk"] for d in body["desks"]] == ["text", "decision"]
    assert all(d["status"] == "pending" for d in body["desks"])
    assert body["artifact"] == {
        "kind": "text",
        "content": "copy",
        "url": None,
        "filename": None,
    }


async def test_a_running_record_says_when_to_come_back(
    app: FastAPI, client: AsyncClient
) -> None:
    record = Verification.submitted(
        artifact=Artifact(kind=ArtifactKind.TEXT, content="copy"), desks=(Desk.TEXT,)
    )
    await app.state.verification_repository.create(record)

    response = await client.get(f"{V1}/verification/{record.id}")

    assert response.headers["retry-after"] == "1"


async def test_an_unknown_id_is_404(client: AsyncClient) -> None:
    response = await client.get(f"{V1}/verification/nope")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["details"] == {"verification_id": "nope"}


# ------------------------------------------------------- the examination run ---


async def test_the_background_task_advances_the_record(client: AsyncClient) -> None:
    """Submit, then read: the task has already run by the time the 202 is in hand.

    An unavailable extractor is injected explicitly, independently of installed
    models. The task must record the failure rather than stay pending.
    """
    with desk_bench(
        {
            Desk.TEXT: StubExaminer(
                Desk.TEXT, raises=ConfigurationError("Extractor unavailable")
            )
        }
    ):
        submitted = await client.post(f"{V1}/verify", json=text_body())
    response = await client.get(f"{V1}/verification/{submitted.json()['id']}")

    body = response.json()
    assert body["status"] == "failed"
    assert body["terminal"] is True
    assert body["failure"] == {
        "code": "configuration_error",
        "message": body["failure"]["message"],
        "desk": "text",
    }
    assert body["completed_at"] is not None


async def test_a_terminal_record_stops_asking_to_be_polled(client: AsyncClient) -> None:
    """The absence of the header is the signal, so a client needs no status table."""
    submitted = await client.post(f"{V1}/verify", json=text_body())
    response = await client.get(f"{V1}/verification/{submitted.json()['id']}")

    assert "retry-after" not in response.headers


async def test_the_failed_desk_is_marked_and_the_rest_are_not(
    client: AsyncClient,
) -> None:
    submitted = await client.post(f"{V1}/verify", json=text_body())
    response = await client.get(f"{V1}/verification/{submitted.json()['id']}")

    progress = {d["desk"]: d["status"] for d in response.json()["desks"]}
    assert progress == {
        "text": "failed",
        "fact-check": "pending",
        "decision": "pending",
    }


async def test_a_failure_is_never_reported_as_an_error(client: AsyncClient) -> None:
    """A failed verification is a successful request. If the body used `error` as
    its key, a client could not tell the two apart by shape."""
    submitted = await client.post(f"{V1}/verify", json=text_body())
    response = await client.get(f"{V1}/verification/{submitted.json()['id']}")

    assert response.status_code == 200
    assert "error" not in response.json()


# ----------------------------------------------------- a completed record ---
# These use desk stubs. Nothing else drives the success path, so without them every
# `from_domain` adapter for a report's interior — annotations, signals, exhibits, the
# verdict's confidence pair — would go unexercised, and a mistyped field name in one
# of them would surface for the first time in front of a real client.


async def test_a_completed_record_reads_back_in_full(client: AsyncClient) -> None:
    stubs = {Desk.TEXT: StubExaminer(Desk.TEXT, report=furnished(Desk.TEXT))}
    with desk_bench(stubs, StubAdjudicator(report=furnished(ADJUDICATOR))):
        submitted = await client.post(f"{V1}/verify", json=text_body(desks=["text"]))

    response = await client.get(f"{V1}/verification/{submitted.json()['id']}")

    body = response.json()
    assert body["status"] == "completed"
    assert body["terminal"] is True
    assert body["failure"] is None
    assert body["completed_at"] is not None
    assert [r["desk"] for r in body["reports"]] == ["text", "decision"]
    assert all(d["status"] == "completed" for d in body["desks"])
    assert "retry-after" not in response.headers


async def test_a_report_carries_its_whole_interior(client: AsyncClient) -> None:
    stubs = {Desk.TEXT: StubExaminer(Desk.TEXT, report=furnished(Desk.TEXT))}
    with desk_bench(stubs, StubAdjudicator(report=furnished(ADJUDICATOR))):
        submitted = await client.post(f"{V1}/verify", json=text_body(desks=["text"]))

    response = await client.get(f"{V1}/verification/{submitted.json()['id']}")

    report = response.json()["reports"][0]
    assert report["ledger"] == [{"key": "Sources", "value": "2"}]
    assert report["annotations"] == [
        {
            "ref": 1,
            "quote": "opened in March",
            "note": "The date is contested.",
            "determination": "CONTESTED",
        }
    ]
    assert report["signals"] == [
        {"label": "Source agreement", "reading": "Split", "weight": 0.5}
    ]
    assert report["exhibits"] == [
        {
            "ref": 1,
            "source": "Example Wire",
            "published": "2026-03-04",
            "relevance": "HIGH",
            "reliability": "VERIFIED",
            "determination": "CONTRADICTED",
            "extract": "The bridge opened in April.",
            "url": "",
            "claim_ref": None,
        }
    ]


async def test_confidence_is_published_both_ways(client: AsyncClient) -> None:
    """The printed string for a record, the number for anything that has to weigh it.

    A verdict carrying only "75%" could not be thresholded or sorted without
    re-parsing the API's own output.
    """
    stubs = {Desk.TEXT: StubExaminer(Desk.TEXT, report=furnished(Desk.TEXT))}
    with desk_bench(stubs, StubAdjudicator(report=furnished(ADJUDICATOR))):
        submitted = await client.post(f"{V1}/verify", json=text_body(desks=["text"]))

    response = await client.get(f"{V1}/verification/{submitted.json()['id']}")

    verdict = response.json()["reports"][0]["verdict"]
    assert verdict["confidence"] == "75%"
    assert verdict["confidence_value"] == 0.75
    assert verdict["determination"] == "CONTESTED"


async def test_the_signed_verdict_is_the_decision_desk_s(client: AsyncClient) -> None:
    """There is no top-level `verdict`: a client reads it off the decision report.

    One source for the string, rather than two with nothing deciding which wins.
    """
    stubs = {Desk.TEXT: StubExaminer(Desk.TEXT, report=furnished(Desk.TEXT))}
    with desk_bench(stubs, StubAdjudicator(report=canned(ADJUDICATOR))):
        submitted = await client.post(f"{V1}/verify", json=text_body(desks=["text"]))

    body = (await client.get(f"{V1}/verification/{submitted.json()['id']}")).json()

    assert "verdict" not in body
    decision = next(r for r in body["reports"] if r["desk"] == "decision")
    assert decision["verdict"]["determination"] == "SUPPORTED"
