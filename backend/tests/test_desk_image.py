"""The image desk: what it files, and what it refuses to conclude.

Driven entirely through the two seams, with a fake reader in place of Tesseract and
a fake detector in place of YOLOv8, so none of this needs the vision stack
installed. That is the point of the split — the libraries recognise things and are
tested where they are called; this file tests the decisions taken around them.

Three of those decisions are the ones worth breaking a build over, and each has a
test below saying so:

* the recovered text goes through the *text* pipeline, unchanged, as a text
  artifact — there is no second verification path for pictures;
* too little text is an insufficiency, not a claim, and the graph is never asked;
* a detected object is a measurement, never a finding. It cannot move a verdict.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

import pytest

from app.core.config import Settings, VisionProvider
from app.core.errors import ProviderUnavailableError, ValidationError
from app.desks.image import ImageDesk
from app.domain import Artifact, ArtifactKind, Desk, Determination
from app.graph.verdict import ClaimRuling, Judgement, Ruling
from app.media import fetch as network
from app.reasoning.answer import Reasoning
from app.vision import detectors, readers
from app.vision.base import Box, Detection, Reading, TextLine

IMAGE = Artifact(kind=ArtifactKind.IMAGE, url="https://example.test/page.png")

#: What the fake fetch returns. Never decoded — no reader here looks at it.
PIXELS = b"\x89PNG\r\n\x1a\n not really"


def configured(**overrides: Any) -> Settings:
    """Test settings. ``_env_file=None`` keeps a developer's ``.env`` out of it."""
    return Settings(_env_file=None, **overrides)


# ------------------------------------------------------------------- doubles ----


class FakeReader:
    """Returns a prepared reading and records the bytes it was handed."""

    name = "fake"

    def __init__(self, reading: Reading) -> None:
        self._reading = reading
        self.seen: list[bytes] = []

    async def read(self, image: bytes) -> Reading:
        self.seen.append(image)
        return self._reading


class FakeDetector:
    """Returns canned detections, or raises, and records the labels asked for."""

    name = "fake"

    def __init__(
        self,
        detections: tuple[Detection, ...] = (),
        *,
        raises: Exception | None = None,
    ) -> None:
        self._detections = detections
        self._raises = raises
        self.asked: list[frozenset[str]] = []

    async def detect(
        self, image: bytes, labels: frozenset[str]
    ) -> tuple[Detection, ...]:
        self.asked.append(labels)
        if self._raises is not None:
            raise self._raises
        return self._detections


class FakeGraph:
    """The compiled workflow, reduced to what the desk reads off an outcome.

    Not the real :class:`app.graph.workflow.VerificationGraph`, which would pull in
    langgraph. Injected through the desk's ``graph`` argument, which exists for
    exactly this.
    """

    def __init__(self, ruling: Ruling, reasoning: tuple[Reasoning, ...] = ()) -> None:
        self._ruling = ruling
        self._reasoning = reasoning
        self.seen: list[Artifact] = []

    async def run(self, artifact: Artifact) -> Any:
        self.seen.append(artifact)
        return _Outcome(self._ruling, self._reasoning)


class _Outcome:
    """The graph's return value, reduced to the two fields a desk reads.

    ``reasoning`` empty is the keyless deployment: no model ran, so the report is
    the arithmetic's alone. Tests that care about the model's prose pass their own.
    """

    def __init__(self, ruling: Ruling, reasoning: tuple[Reasoning, ...] = ()) -> None:
        self.ruling = ruling
        self.reasoning = reasoning


@contextmanager
def bench(
    reader: FakeReader,
    detector: FakeDetector | None = None,
    *,
    data: bytes = PIXELS,
) -> Iterator[None]:
    """Substitute both vision seams and the fetch, then put them all back.

    Both, unconditionally, even when a test says nothing about detection. A reading
    whose text happens to name a COCO class would otherwise resolve the real
    detector, and ultralytics resolves a bare weights filename by downloading it —
    so an incautious fixture would turn ``pytest`` into a network fetch.

    The registries are module-level singletons and the real Tesseract reader is
    registered at import, so this restores what it displaced rather than clearing
    the key. Leaving the seam empty would turn every later resolve in the session
    into a 501 — the same trap :func:`tests.stubs.desk_bench` documents.
    """
    substitute = detector if detector is not None else FakeDetector()
    was_reader = readers.factory(VisionProvider.TESSERACT)
    was_detector = detectors.factory(VisionProvider.YOLO)
    original_fetch = network.fetch

    async def served(
        url: str,
        *,
        timeout: float,
        limit: int,
        accept: tuple[str, ...] = (),
        allow_private: bool = False,
    ) -> bytes:
        return data

    readers.register(VisionProvider.TESSERACT, lambda _settings: reader)
    detectors.register(VisionProvider.YOLO, lambda _settings: substitute)
    network.fetch = served
    try:
        yield
    finally:
        network.fetch = original_fetch
        if was_reader is not None:
            readers.register(VisionProvider.TESSERACT, was_reader)
        if was_detector is not None:
            detectors.register(VisionProvider.YOLO, was_detector)


def desk(
    reader: FakeReader,
    ruling: Ruling | None = None,
    *,
    settings: Settings | None = None,
) -> tuple[ImageDesk, FakeGraph]:
    graph = FakeGraph(ruling if ruling is not None else RULING)
    built = ImageDesk(
        settings=settings if settings is not None else configured(),
        graph=cast("Any", graph),
    )
    return built, graph


# ------------------------------------------------------------------ fixtures ----


def line(text: str, y: int, *, block: int = 1, conf: float = 0.94) -> TextLine:
    return TextLine(text, Box(40, y, 8 * len(text), 24), conf, block=block)


#: A headline over two physical lines, then a caption in its own block — the shape
#: a screenshot of a news page produces. ``text`` is what ``compose`` makes of it.
PAGE = Reading(
    text="The central bank held the rate at 5.25%.\n\nPhotograph: Reuters",
    lines=(
        line("The central bank", 20),
        line("held the rate at 5.25%.", 54),
        line("Photograph: Reuters", 400, block=2, conf=0.71),
    ),
    width=800,
    height=600,
    confidence=0.9,
    variant="threshold",
    rotation=1.4,
)

CROWD = Reading(
    text="A crowd of twelve gathered outside the courthouse on Tuesday.",
    lines=(line("A crowd of twelve gathered outside the courthouse on Tuesday.", 30),),
    width=800,
    height=600,
    confidence=0.88,
)

BLANK = Reading(
    text="Rate held",
    lines=(line("Rate held", 10),),
    width=80,
    height=40,
    confidence=0.5,
)

RULING = Ruling(
    judgement=Judgement.SUPPORTED,
    confidence=0.82,
    headline="The rate was held",
    rationale="Two independent outlets report the same decision.",
    claims=(
        ClaimRuling(
            ref=1,
            claim="The central bank held the rate at 5.25%.",
            judgement=Judgement.SUPPORTED,
            confidence=0.82,
        ),
    ),
)


# ------------------------------------------------------------- the pipeline ----


async def test_the_recovered_text_is_submitted_as_a_text_artifact() -> None:
    """The whole design, in one assertion.

    An image is a delivery mechanism for a claim, not a different kind of claim, so
    what reaches the graph is the OCR text as prose — not the image, and not a
    reduced summary of it. Anything else would mean a second verification path that
    has to be kept in agreement with the first.
    """
    reader = FakeReader(PAGE)
    built, graph = desk(reader)

    with bench(reader):
        await built.examine(IMAGE)

    assert [a.kind for a in graph.seen] == [ArtifactKind.TEXT]
    assert graph.seen[0].content == PAGE.text


async def test_the_reader_is_handed_the_fetched_bytes() -> None:
    reader = FakeReader(PAGE)
    built, _ = desk(reader)

    with bench(reader, data=b"the fetched image"):
        await built.examine(IMAGE)

    assert reader.seen == [b"the fetched image"]


async def test_the_desks_verdict_is_the_graphs_ruling() -> None:
    reader = FakeReader(PAGE)
    built, _ = desk(reader)

    with bench(reader):
        report = await built.examine(IMAGE)

    assert report.desk is Desk.IMAGE
    assert report.verdict.determination is Determination.SUPPORTED
    assert report.verdict.headline == "The rate was held"
    assert report.verdict.confidence == pytest.approx(0.82)


async def test_a_refuted_ruling_reaches_the_wire_as_contradicted() -> None:
    """``Judgement`` and ``Determination`` are different vocabularies."""
    refuted = Ruling(
        judgement=Judgement.REFUTED,
        confidence=0.91,
        headline="No such decision was taken",
        rationale="The published minutes record a cut.",
    )
    reader = FakeReader(PAGE)
    built, _ = desk(reader, refuted)

    with bench(reader):
        report = await built.examine(IMAGE)

    assert report.verdict.determination is Determination.CONTRADICTED


async def test_an_image_artifact_without_a_url_is_a_validation_error() -> None:
    """Nothing to read, and not a finding about anything."""
    reader = FakeReader(PAGE)
    built, _ = desk(reader)

    with bench(reader), pytest.raises(ValidationError, match="needs a URL"):
        await built.examine(Artifact(kind=ArtifactKind.IMAGE, content="pasted"))


# ------------------------------------------------------------ nothing to read ----


async def test_an_unreadable_image_is_insufficient_not_false() -> None:
    """A picture with no legible text says nothing, which is not a claim to rule on.

    Reporting anything else would publish a determination about a claim that was
    never extracted, let alone checked.
    """
    reader = FakeReader(BLANK)
    built, _ = desk(reader)

    with bench(reader):
        report = await built.examine(IMAGE)

    assert report.verdict.determination is Determination.INSUFFICIENT
    assert report.verdict.confidence == 0.0
    assert report.annotations == ()


async def test_an_unreadable_image_never_reaches_the_graph() -> None:
    """The gate is before the pipeline, not inside it.

    Nine characters of OCR noise put through claim extraction and web search costs
    a search-provider call to conclude what the character count already said.
    """
    reader = FakeReader(BLANK)
    built, graph = desk(reader)

    with bench(reader):
        await built.examine(IMAGE)

    assert graph.seen == []


async def test_the_threshold_is_configurable() -> None:
    reader = FakeReader(BLANK)
    built, graph = desk(reader, settings=configured(IMAGE_MIN_TEXT_CHARS=5))

    with bench(reader):
        report = await built.examine(IMAGE)

    assert graph.seen != []
    assert report.verdict.determination is Determination.SUPPORTED


# ---------------------------------------------------------------- detection ----


async def test_no_detector_runs_for_text_that_names_no_object() -> None:
    """The gate that keeps torch off the critical path.

    Checked before the detector is resolved, because what is being avoided is the
    model load and its first-use weights download, not the inference.
    """
    reader = FakeReader(PAGE)
    detector = FakeDetector()
    built, _ = desk(reader)

    with bench(reader, detector):
        report = await built.examine(IMAGE)

    assert detector.asked == []
    assert [s.label for s in report.signals] == ["Text recovered"]


async def test_a_named_object_is_the_only_thing_asked_for() -> None:
    """A crowd asks for ``person``. It does not ask for the other 79 classes.

    A detector free to report everything it sees fills the record with furniture
    that bears on nothing.
    """
    reader = FakeReader(CROWD)
    detector = FakeDetector((Detection("person", 0.9, Box(10, 10, 40, 80)),))
    built, _ = desk(reader)

    with bench(reader, detector):
        await built.examine(IMAGE)

    assert detector.asked == [frozenset({"person"})]


async def test_detection_can_be_switched_off_entirely() -> None:
    reader = FakeReader(CROWD)
    detector = FakeDetector()
    built, _ = desk(reader, settings=configured(IMAGE_DETECTION_ENABLED=False))

    with bench(reader, detector):
        await built.examine(IMAGE)

    assert detector.asked == []


async def test_a_detection_is_reported_as_a_measurement_not_a_finding() -> None:
    """The constraint that keeps this honest.

    A model counting two people in a frame does not refute "twelve gathered": the
    frame is not the world and the crop is not the frame. So a detection arrives as
    a signal carrying the detector's own confidence, and the determination stays
    the one the evidence produced.
    """
    reader = FakeReader(CROWD)
    detector = FakeDetector(
        (
            Detection("person", 0.91, Box(10, 10, 40, 80)),
            Detection("person", 0.77, Box(60, 12, 38, 78)),
        )
    )
    built, _ = desk(reader)

    with bench(reader, detector):
        report = await built.examine(IMAGE)

    assert report.verdict.determination is Determination.SUPPORTED
    found = next(s for s in report.signals if s.label == "Person")
    assert found.reading == "2 detected"
    assert found.weight == pytest.approx(0.91)


async def test_a_detector_failure_does_not_lose_the_reading() -> None:
    """Ultralytics not being installed is not a reason to drop a checked claim."""
    reader = FakeReader(CROWD)
    detector = FakeDetector(raises=ProviderUnavailableError("no weights"))
    built, _ = desk(reader)

    with bench(reader, detector):
        report = await built.examine(IMAGE)

    assert report.verdict.determination is Determination.SUPPORTED
    assert [s.label for s in report.signals] == ["Text recovered"]


# -------------------------------------------------------- what a reader sees ----


async def test_every_annotation_quotes_the_text_verbatim() -> None:
    """The frontend does ``copy.indexOf(annotation.quote)`` and drops a miss.

    A quote stitched together from lines that were not adjacent on the page — or
    taken from the ruling's normalised claim string rather than from the OCR
    output — appears nowhere in the text, and the marker silently never renders.
    """
    reader = FakeReader(PAGE)
    built, _ = desk(reader)

    with bench(reader):
        report = await built.examine(IMAGE)

    assert report.annotations
    for annotation in report.annotations:
        assert annotation.quote in PAGE.text


async def test_an_annotation_points_at_the_claim_it_came_from() -> None:
    reader = FakeReader(PAGE)
    built, _ = desk(reader)

    with bench(reader):
        report = await built.examine(IMAGE)

    annotation = report.annotations[0]
    assert annotation.ref == 1
    assert annotation.determination is Determination.SUPPORTED
    assert annotation.quote == "The central bank held the rate at 5.25%."


async def test_a_line_belonging_to_no_claim_is_not_annotated() -> None:
    """The caption is on the page. It is not part of the claim that was checked."""
    reader = FakeReader(PAGE)
    built, _ = desk(reader)

    with bench(reader):
        report = await built.examine(IMAGE)

    assert len(report.annotations) == 1
    assert "Reuters" not in report.annotations[0].quote


async def test_regions_are_percentages_of_the_submitted_image() -> None:
    """Pixels would line up at exactly one zoom level."""
    reader = FakeReader(PAGE)
    built, _ = desk(reader)

    with bench(reader):
        report = await built.examine(IMAGE)

    detail = report.detail
    assert detail is not None
    assert (detail.width, detail.height) == (800, 600)
    first = detail.regions[0]
    assert first.x == pytest.approx(5.0)
    assert first.y == pytest.approx(100 * 20 / 600)
    assert all(0.0 <= r.x <= 100.0 for r in detail.regions)


async def test_a_region_carries_the_ruling_its_line_was_read_into() -> None:
    """Which is what lets the reader highlight the box a verdict came from."""
    reader = FakeReader(PAGE)
    built, _ = desk(reader)

    with bench(reader):
        report = await built.examine(IMAGE)

    assert report.detail is not None
    refs = [r.ref for r in report.detail.regions]
    assert refs == [1, 1, 0]


async def test_a_detected_object_gets_its_own_region() -> None:
    reader = FakeReader(CROWD)
    detector = FakeDetector((Detection("person", 0.91, Box(10, 10, 40, 80)),))
    built, _ = desk(reader)

    with bench(reader, detector):
        report = await built.examine(IMAGE)

    assert report.detail is not None
    assert report.detail.regions[-1].label == "person 91%"


async def test_the_detail_carries_the_text_that_was_checked() -> None:
    """So a record can be re-read without the image, which may be gone."""
    reader = FakeReader(PAGE)
    built, _ = desk(reader)

    with bench(reader):
        report = await built.examine(IMAGE)

    assert report.detail is not None
    assert report.detail.text == PAGE.text


# ------------------------------------------------------------------- ledger ----


async def test_the_ledger_records_how_the_page_was_read() -> None:
    """Which is what makes a poor reading diagnosable from a stored record.

    Without the preparation and the deskew angle, a bad result is only explicable
    by re-running with the original image in hand.
    """
    reader = FakeReader(PAGE)
    built, _ = desk(reader)

    with bench(reader):
        report = await built.examine(IMAGE)

    ledger = {entry.key: entry.value for entry in report.ledger}
    assert ledger["Dimensions"] == "800 x 600"
    assert ledger["Lines read"] == "3"
    assert ledger["Words read"] == "10"
    assert ledger["Read confidence"] == "90%"
    assert ledger["Preparation"] == "threshold"
    assert ledger["Deskewed"] == "1.4°"
    assert ledger["Claims ruled"] == "1"


async def test_a_level_page_reports_no_deskew() -> None:
    """Rather than a row reading zero degrees, which says nothing."""
    reader = FakeReader(CROWD)
    built, _ = desk(reader)

    with bench(reader):
        report = await built.examine(IMAGE)

    assert "Deskewed" not in {entry.key for entry in report.ledger}


async def test_the_object_count_appears_only_when_detection_ran() -> None:
    reader = FakeReader(CROWD)
    detector = FakeDetector((Detection("person", 0.91, Box(10, 10, 40, 80)),))
    built, _ = desk(reader)

    with bench(reader, detector):
        with_objects = await built.examine(IMAGE)
    with bench(reader, FakeDetector()):
        without = await built.examine(IMAGE)

    assert ("Objects detected", "1") in {(e.key, e.value) for e in with_objects.ledger}
    assert "Objects detected" not in {e.key for e in without.ledger}
