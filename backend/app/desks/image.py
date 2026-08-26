"""The image desk: read the page, then verify what it says.

The pipeline this desk feeds is the text one. There is no separate image
verification: OCR recovers what the picture claims, and the existing graph — claim
extraction, search, fact-check lookup, evidence scoring, source credibility,
contradiction detection, the judge — rules on it exactly as it would on the same
sentence pasted in as prose. That is the point. An image is a delivery mechanism
for a claim, not a different kind of claim.

Object detection is the exception, and it is deliberately kept out of the verdict.
See :meth:`ImageDesk._look`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import Settings, get_settings
from app.core.errors import ValidationError, VeritasError
from app.desks.anchors import attach
from app.desks.graph import compiled, model_ledger, readings
from app.domain import (
    Artifact,
    ArtifactKind,
    Desk,
    DeskReport,
    Determination,
    ImageDetail,
    LedgerEntry,
    PlateRegion,
    Signal,
    Verdict,
)
from app.graph.verdict import Ruling, as_determination
from app.media import fetch
from app.vision import get_image_reader, get_object_detector
from app.vision.base import Box, Detection, Reading
from app.vision.relevance import wanted

if TYPE_CHECKING:
    from app.graph.workflow import Outcome, VerificationGraph

logger = logging.getLogger(__name__)


class ImageDesk:
    """Examines images: text recovered by OCR, ruled on by the text pipeline."""

    desk = Desk.IMAGE
    kinds = frozenset({ArtifactKind.IMAGE})

    def __init__(
        self, *, settings: Settings, graph: VerificationGraph | None = None
    ) -> None:
        self._settings = settings
        self._own = graph

    async def examine(
        self, artifact: Artifact, *, verification_id: str | None = None
    ) -> DeskReport:
        data = await self._fetch(artifact)
        reading = await get_image_reader(self._settings).read(data)

        if len(reading.text.strip()) < self._settings.IMAGE_MIN_TEXT_CHARS:
            return self._unread(reading)

        outcome = await self._graph().run(
            Artifact(kind=ArtifactKind.TEXT, content=reading.text)
        )
        detections = await self._look(data, reading)
        return self._filed(reading, outcome, detections)

    # ------------------------------------------------------------ steps ----

    async def _fetch(self, artifact: Artifact) -> bytes:
        if not artifact.url:
            raise ValidationError(
                "An image artifact needs a URL to fetch.",
                details={"desk": str(self.desk)},
            )
        return await fetch.fetch(
            artifact.url,
            timeout=self._settings.MEDIA_FETCH_TIMEOUT_SECONDS,
            limit=self._settings.MAX_UPLOAD_BYTES,
            accept=("image/",),
            allow_private=self._settings.MEDIA_ALLOW_PRIVATE_HOSTS,
        )

    async def _look(self, data: bytes, reading: Reading) -> tuple[Detection, ...]:
        """Detect objects, but only the ones the text asked about.

        Two gates, and the second is the interesting one. ``wanted`` returns empty
        unless the recovered text names something in the detector's vocabulary, so
        an image of a quotation never loads the weights at all — checked before the
        model is touched, because the cost being avoided is the load and its
        first-use download.

        A detector failure is logged and discarded rather than raised. The reading
        is the deliverable here; losing a verified claim because ultralytics is not
        installed would be the wrong trade.
        """
        if not self._settings.IMAGE_DETECTION_ENABLED:
            return ()

        labels = wanted(reading.text)
        if not labels:
            return ()

        try:
            return await get_object_detector(self._settings).detect(data, labels)
        except VeritasError as exc:
            logger.warning(
                "object detection skipped: %s", exc.message, extra={"labels": labels}
            )
            return ()

    def _graph(self) -> VerificationGraph:
        return self._own or compiled(self._settings)

    # ----------------------------------------------------------- filing ----

    def _unread(self, reading: Reading) -> DeskReport:
        """Nothing legible on the page. Not a finding about the claim."""
        return DeskReport(
            desk=self.desk,
            verdict=Verdict(
                determination=Determination.INSUFFICIENT,
                headline="No readable text recovered",
                rationale=(
                    "Optical character recognition returned too little text to "
                    "extract a claim from, so nothing was submitted for "
                    "verification. The image may carry no text, or none this "
                    "reader could resolve."
                ),
                confidence=0.0,
            ),
            ledger=self._ledger(reading, None, ()),
            signals=(self._recovered(reading),),
            detail=self._detail(reading, {}, ()),
        )

    def _filed(
        self,
        reading: Reading,
        outcome: Outcome,
        detections: tuple[Detection, ...],
    ) -> DeskReport:
        ruling = outcome.ruling
        anchors, annotations = attach(
            [(line.text, line.block) for line in reading.lines],
            ruling.claims,
            readings=readings(ruling.claims, outcome.reasoning),
        )
        return DeskReport(
            desk=self.desk,
            verdict=Verdict(
                determination=as_determination(ruling.judgement),
                headline=ruling.headline,
                rationale=ruling.rationale,
                confidence=ruling.confidence,
            ),
            ledger=(
                *self._ledger(reading, ruling, detections),
                *model_ledger(outcome.reasoning),
            ),
            annotations=annotations,
            signals=self._signals(reading, detections),
            detail=self._detail(reading, anchors, detections),
        )

    def _ledger(
        self,
        reading: Reading,
        ruling: Ruling | None,
        detections: tuple[Detection, ...],
    ) -> tuple[LedgerEntry, ...]:
        entries = [
            LedgerEntry("Dimensions", f"{reading.width} x {reading.height}"),
            LedgerEntry("Lines read", str(len(reading.lines))),
            LedgerEntry("Words read", str(reading.words)),
            LedgerEntry("Read confidence", f"{round(reading.confidence * 100)}%"),
            LedgerEntry("Preparation", reading.variant),
        ]
        if reading.rotation:
            entries.append(LedgerEntry("Deskewed", f"{reading.rotation:.1f}°"))
        if ruling is not None:
            entries.append(LedgerEntry("Claims ruled", str(len(ruling.claims))))
        if detections:
            entries.append(LedgerEntry("Objects detected", str(len(detections))))
        return tuple(entries)

    def _signals(
        self, reading: Reading, detections: tuple[Detection, ...]
    ) -> tuple[Signal, ...]:
        """Measurements, never a verdict.

        A detection is reported as an observation and weighted by the detector's
        own confidence, and it is not allowed to move the determination. A model
        counting eight people in a frame does not refute "twelve were arrested":
        the frame is not the world, and the crop is not the frame.
        """
        signals = [self._recovered(reading)]
        for label, found in _counted(detections):
            signals.append(
                Signal(
                    label=label.title(),
                    reading=f"{len(found)} detected",
                    weight=max(d.confidence for d in found),
                )
            )
        return tuple(signals)

    def _recovered(self, reading: Reading) -> Signal:
        return Signal(
            label="Text recovered",
            reading=f"{reading.words} words",
            weight=min(1.0, max(0.0, reading.confidence)),
        )

    def _detail(
        self,
        reading: Reading,
        anchors: dict[int, int],
        detections: tuple[Detection, ...],
    ) -> ImageDetail:
        regions = [
            _region(line.box, reading, anchors.get(index, 0), line.text[:80])
            for index, line in enumerate(reading.lines)
        ]
        regions.extend(
            _region(
                found.box, reading, 0, f"{found.label} {found.confidence:.0%}"
            )
            for found in detections
        )
        return ImageDetail(
            width=reading.width,
            height=reading.height,
            text=reading.text,
            regions=tuple(regions),
        )


def _region(box: Box, reading: Reading, ref: int, label: str) -> PlateRegion:
    x, y, w, h = box.within(reading.width, reading.height)
    return PlateRegion(ref=ref, x=x, y=y, w=w, h=h, label=label)


def _counted(
    detections: tuple[Detection, ...],
) -> tuple[tuple[str, tuple[Detection, ...]], ...]:
    grouped: dict[str, list[Detection]] = {}
    for found in detections:
        grouped.setdefault(found.label, []).append(found)
    return tuple((label, tuple(grouped[label])) for label in sorted(grouped))


def build(settings: Settings | None = None) -> ImageDesk:
    """Factory for the registry, which resolves desks with no arguments."""
    return ImageDesk(settings=settings or get_settings())
