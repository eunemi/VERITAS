"""The text desk: what it reads, what it marks, and what it refuses to conclude.

This desk answers "what does this document assert, and which of those assertions could
anyone check?" — never "and are they so?". That second question is the fact-check
desk's, and the two open on the same artifact so the two readings stay separable.

The properties worth breaking a build over, each with a test below:

* it never files an affirmative determination. A desk that has checked nothing must
  not file a finding that reads as though it had, so every verdict here is
  ``REQUIRES_VERIFICATION`` or ``INSUFFICIENT`` and every confidence is zero;
* a submitted *claim* is taken as written and never screened, because screening it
  would let this desk set aside a claim the fact-check desk goes on to check anyway;
* an unfit claim is annotated with the reason it was set aside rather than dropped —
  a reader has to be able to see what was not checked;
* the extractor is built inside the method that needs it, which is what keeps
  ``app.desks`` importable from ``app.services`` without closing a cycle.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.config import Settings
from app.desks import examiners
from app.desks.base import ArtifactDesk
from app.desks.text import LEDGER_QUOTE, TextDesk, build
from app.domain import (
    Artifact,
    ArtifactKind,
    Desk,
    Determination,
    Entity,
    ExtractedClaim,
    Extraction,
    Keyword,
    Unfit,
    can_examine,
)
from tests.stubs import (
    SAMPLE_TEXT,
    StubClaimExtractor,
    extractor_bench,
    sample_extraction,
)

#: Every determination this desk is permitted to reach.
ALLOWED = frozenset({Determination.REQUIRES_VERIFICATION, Determination.INSUFFICIENT})


def configured(**overrides: Any) -> Settings:
    """Test settings. ``_env_file=None`` keeps a developer's ``.env`` out of it."""
    return Settings(_env_file=None, **overrides)


def desk(extraction: Extraction | None = None, **overrides: Any) -> TextDesk:
    """The desk with a stub extractor injected, so no NLP library is needed."""
    return TextDesk(
        settings=configured(**overrides),
        extractor=StubClaimExtractor(  # type: ignore[arg-type]
            extraction=extraction if extraction is not None else sample_extraction()
        ),
    )


def seated(stub: StubClaimExtractor) -> TextDesk:
    """The desk carrying a named stub, for the tests that then inspect the stub."""
    return TextDesk(settings=configured(), extractor=stub)  # type: ignore[arg-type]


def text(body: str = SAMPLE_TEXT) -> Artifact:
    return Artifact(kind=ArtifactKind.TEXT, content=body)


def extracted(
    *claims: ExtractedClaim,
    entities: tuple[Entity, ...] = (),
    keywords: tuple[Keyword, ...] = (),
    sentences: int = 1,
) -> Extraction:
    return Extraction(
        claims=claims, entities=entities, keywords=keywords, sentences=sentences
    )


def unfit(body: str, *, reason: str) -> ExtractedClaim:
    return ExtractedClaim(
        ref=1,
        text=body,
        quote=body,
        start=0,
        end=len(body),
        checkable=False,
        reason=reason,
    )


def claim(body: str = "The bridge opened in March 2026.") -> Artifact:
    return Artifact(kind=ArtifactKind.CLAIM, content=body)


def ledger_of(report: Any) -> dict[str, str]:
    return {entry.key: entry.value for entry in report.ledger}


# ------------------------------------------------------------------- the seam ----


def test_it_is_the_registered_text_examiner() -> None:
    assert examiners.factory(Desk.TEXT) is not None
    assert isinstance(examiners.resolve(Desk.TEXT), TextDesk)


def test_it_satisfies_the_protocol() -> None:
    made = build(configured())
    assert isinstance(made, ArtifactDesk)
    assert made.desk is Desk.TEXT


def test_it_claims_the_three_prose_kinds() -> None:
    assert TextDesk.kinds == frozenset(
        {ArtifactKind.TEXT, ArtifactKind.CLAIM, ArtifactKind.URL}
    )
    for kind in TextDesk.kinds:
        assert can_examine(Desk.TEXT, kind)
    assert not can_examine(Desk.TEXT, ArtifactKind.IMAGE)


async def test_the_extractor_is_built_on_use_and_not_at_import() -> None:
    """The lazy build is not a style choice: ``app.services`` imports the orchestrator,
    which imports this package for the registries, so a module-scope import of the
    service closes a cycle and leaves whichever was imported first half-initialised.
    """
    stub = StubClaimExtractor(extraction=sample_extraction())
    with extractor_bench(stub):
        report = await TextDesk(settings=configured()).examine(text())
    assert stub.seen == [SAMPLE_TEXT]
    assert report.verdict.determination is Determination.REQUIRES_VERIFICATION


async def test_an_injected_extractor_is_preferred_over_a_built_one() -> None:
    own = StubClaimExtractor(extraction=sample_extraction())
    other = StubClaimExtractor(extraction=sample_extraction())
    with extractor_bench(other):
        await seated(own).examine(text())
    assert own.seen == [SAMPLE_TEXT]
    assert other.seen == []


# ---------------------------------------------------- what it will not conclude ----


@pytest.mark.parametrize(
    "artifact",
    [
        text(),
        claim(),
        text("   "),
        Artifact(kind=ArtifactKind.URL, url="https://example.test/story"),
    ],
)
async def test_it_never_files_an_affirmative_determination(
    artifact: Artifact,
) -> None:
    report = await desk().examine(artifact)
    assert report.verdict.determination in ALLOWED


@pytest.mark.parametrize("artifact", [text(), claim(), text("")])
async def test_confidence_is_always_zero(artifact: Artifact) -> None:
    """Zero in both directions. This desk states what it read; confidence belongs to a
    finding about a claim, and it has none."""
    report = await desk().examine(artifact)
    assert report.verdict.confidence == 0.0


async def test_no_annotation_claims_a_finding_about_truth() -> None:
    report = await desk().examine(text())
    assert report.annotations != ()
    for annotation in report.annotations:
        assert annotation.determination in ALLOWED


# ------------------------------------------------------------- nothing to read ----


@pytest.mark.parametrize("body", ["", "   ", "\n\t "])
async def test_empty_prose_is_an_insufficiency(body: str) -> None:
    report = await desk().examine(text(body))
    assert report.verdict.determination is Determination.INSUFFICIENT
    assert report.verdict.headline == "No prose to read"
    assert ledger_of(report) == {"Characters read": "0"}
    assert report.annotations == ()


async def test_a_url_says_the_fetch_is_not_built_rather_than_that_it_was_empty() -> (
    None
):
    """Two different states, and a reader who cannot tell them apart is misinformed."""
    report = await desk().examine(
        Artifact(kind=ArtifactKind.URL, url="https://example.test/story")
    )
    assert "fetching the article behind it is not built yet" in (
        report.verdict.rationale
    )


async def test_empty_prose_never_reaches_the_extractor() -> None:
    stub = StubClaimExtractor(extraction=sample_extraction())
    await seated(stub).examine(text(""))
    assert stub.seen == []


# ---------------------------------------------------------- a submitted claim ----


async def test_a_submitted_claim_is_taken_as_written() -> None:
    stub = StubClaimExtractor(extraction=sample_extraction())
    body = "Rainfall in Chennai set a July record in 2025."
    report = await seated(stub).examine(Artifact(kind=ArtifactKind.CLAIM, content=body))

    # Never screened: screening it would let this desk set aside a claim the
    # fact-check desk goes on to check anyway.
    assert stub.seen == []
    assert report.verdict.determination is Determination.REQUIRES_VERIFICATION
    assert ledger_of(report) == {
        "Characters read": str(len(body)),
        "Claims found": "1",
        "Extraction": "taken as submitted",
    }


async def test_a_submitted_claim_is_annotated_verbatim() -> None:
    """The frontend locates a span with ``indexOf``, so a paraphrase never appears."""
    body = "Rainfall in Chennai set a July record in 2025."
    report = await desk().examine(Artifact(kind=ArtifactKind.CLAIM, content=body))
    assert len(report.annotations) == 1
    assert report.annotations[0].quote == body
    assert report.annotations[0].ref == 1


async def test_a_submitted_claim_is_stripped_before_it_is_measured() -> None:
    report = await desk().examine(claim("  Bank Rate held at 4.75%.  "))
    assert report.annotations[0].quote == "Bank Rate held at 4.75%."
    assert ledger_of(report)["Characters read"] == "24"


# ------------------------------------------------------------------ extraction ----


async def test_a_checkable_claim_is_marked_and_passed_on() -> None:
    report = await desk().examine(text())
    assert report.verdict.determination is Determination.REQUIRES_VERIFICATION
    assert report.verdict.headline == "1 checkable claim(s) found"

    passed = [
        a
        for a in report.annotations
        if a.determination is Determination.REQUIRES_VERIFICATION
    ]
    assert [a.quote for a in passed] == ["The bridge opened in March 2026"]
    assert passed[0].note == "Checkable assertion; passed on for checking."


async def test_an_unfit_claim_is_annotated_with_its_reason_not_dropped() -> None:
    report = await desk().examine(text())
    aside = [
        a for a in report.annotations if a.determination is Determination.INSUFFICIENT
    ]
    assert [a.quote for a in aside] == ["It is a beautiful bridge"]
    assert aside[0].note == f"Set aside: {Unfit.OPINION}."


async def test_an_unfit_claim_with_no_stated_reason_still_says_something() -> None:
    extraction = extracted(unfit("Something happened.", reason=""))
    report = await desk(extraction).examine(text("Something happened."))
    assert report.annotations[0].note == "Set aside: not a checkable claim."


async def test_prose_with_no_checkable_claim_is_an_insufficiency() -> None:
    """Copy can be entirely opinion without anything being wrong with it, so this is a
    finding about the writing and not about its truth."""
    extraction = extracted(unfit("It is a beautiful bridge.", reason=Unfit.OPINION))
    report = await desk(extraction).examine(text("It is a beautiful bridge."))
    assert report.verdict.determination is Determination.INSUFFICIENT
    assert report.verdict.headline == "No checkable claim found"
    assert "not about its truth" in report.verdict.rationale


async def test_an_extraction_that_found_nothing_at_all_files_cleanly() -> None:
    report = await desk(extracted(sentences=3)).examine(text("Hello."))
    assert report.verdict.determination is Determination.INSUFFICIENT
    assert report.annotations == ()
    ledger = ledger_of(report)
    assert ledger["Assertions found"] == "0"
    assert ledger["Claims to check"] == "0"
    # Not a ZeroDivisionError, and not a misleading 1.0 either.
    assert [s.weight for s in report.signals] == [0.0]


# ---------------------------------------------------------------- the ledger ----


async def test_the_ledger_counts_what_was_read_and_what_was_set_aside() -> None:
    report = await desk().examine(text())
    ledger = ledger_of(report)
    assert ledger["Sentences read"] == "2"
    assert ledger["Assertions found"] == "2"
    assert ledger["Claims to check"] == "1"
    assert ledger["Claims set aside"] == "1"
    assert ledger["Named entities"] == "March 2026"
    assert ledger["Subject terms"] == "bridge, march"


async def test_entity_and_term_rows_are_omitted_rather_than_left_empty() -> None:
    extraction = extracted(*sample_extraction().claims, sentences=2)
    ledger = ledger_of(await desk(extraction).examine(text()))
    assert "Named entities" not in ledger
    assert "Subject terms" not in ledger


async def test_a_long_entity_list_is_clipped_rather_than_dumped() -> None:
    extraction = extracted(
        *sample_extraction().claims,
        entities=tuple(
            Entity(text=f"Organisation number {n}", label="ORG", start=0, end=1)
            for n in range(12)
        ),
        keywords=(Keyword(term="x" * 200, score=1.0),),
        sentences=2,
    )
    ledger = ledger_of(await desk(extraction).examine(text()))
    for row in ("Named entities", "Subject terms"):
        assert len(ledger[row]) == LEDGER_QUOTE
        assert ledger[row].endswith("…")


async def test_the_checkable_share_is_reported_as_a_fraction() -> None:
    report = await desk().examine(text())
    assert [(s.label, s.reading, s.weight) for s in report.signals] == [
        ("Checkable share", "1 of 2 assertion(s)", 0.5)
    ]
