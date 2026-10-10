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

import asyncio
import logging
from dataclasses import replace
from typing import TYPE_CHECKING

import anyio.to_thread

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError, ValidationError, VeritasError
from app.desks.anchors import attach
from app.desks.graph import compiled, model_ledger, readings
from app.domain import (
    Artifact,
    ArtifactKind,
    Desk,
    DeskReport,
    Determination,
    Dossier,
    Exhibit,
    ImageDetail,
    LedgerEntry,
    PlateRegion,
    Relevance,
    Reliability,
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
        if (
            self._settings.OPENAI_API_KEY
            or self._settings.VISION_API_KEY
            or self._settings.GOOGLE_VISION_API_KEY
        ):
            return await self._inspect(data, artifact)
        try:
            reading = await get_image_reader(self._settings).read(data)
        except ConfigurationError as exc:
            logger.warning("Image desk missing OCR dependencies: %s", exc)
            return self._ocr_unavailable()

        if len(reading.text.strip()) < self._settings.IMAGE_MIN_TEXT_CHARS:
            return self._unread(reading)

        outcome = await self._graph().run(
            Artifact(kind=ArtifactKind.TEXT, content=reading.text)
        )
        detections = await self._look(data, reading)
        return self._filed(reading, outcome, detections)

    # ------------------------------------------------------------ steps ----

    async def _inspect(self, data: bytes, artifact: Artifact) -> DeskReport:
        from app.desks.factcheck import claim_annotations, evidence_exhibits
        from app.services.claims import ClaimExtractionService
        from app.services.research import WebResearchService
        from app.vision.context import describe, prepare, reverse_matches

        prepared = await anyio.to_thread.run_sync(prepare, data)
        scene_result, matches_result = await asyncio.gather(
            describe(prepared, self._settings),
            reverse_matches(prepared, self._settings),
            return_exceptions=True,
        )
        limitations = [
            "Visual observations and editable file metadata cannot prove "
            "that pixels are authentic or AI-generated."
        ]
        if isinstance(scene_result, BaseException):
            if not isinstance(scene_result, VeritasError):
                raise scene_result
            limitations.append(
                f"Visual description unavailable ({scene_result.code}). "
                "Check VISION_MODEL and its API credentials."
            )
            scene = None
            try:
                reading = await get_image_reader(self._settings).read(data)
            except VeritasError:
                reading = Reading(
                    text="",
                    lines=(),
                    width=prepared.width,
                    height=prepared.height,
                    confidence=0,
                )
                limitations.append(
                    "OCR was also unavailable; no image text could be recovered."
                )
        else:
            scene = scene_result
            limitations.extend(scene.limitations)
            reading = Reading(
                text=scene.text,
                lines=(),
                width=prepared.width,
                height=prepared.height,
                confidence=0,
                variant="vision model",
            )

        if isinstance(matches_result, BaseException):
            if not isinstance(matches_result, VeritasError):
                raise matches_result
            matches: tuple[Exhibit, ...] = ()
            web_status = (
                "not_configured"
                if isinstance(matches_result, ConfigurationError)
                else "failed"
            )
            limitations.append(
                "Reverse-image lookup was not completed. "
                + (
                    matches_result.message
                    if isinstance(matches_result, ConfigurationError)
                    else "The provider was unavailable."
                )
            )
        else:
            matches = matches_result
            web_status = "searched"

        copy = "\n\n".join(
            part
            for part in (reading.text.strip(), (artifact.content or "").strip())
            if part
        )

        async def check_claims() -> Outcome | None:
            return (
                await self._graph().run(Artifact(kind=ArtifactKind.TEXT, content=copy))
                if copy
                else None
            )

        async def search_scene() -> Dossier | None:
            if scene is None or not scene.search_queries:
                return None
            return await WebResearchService(
                settings=self._settings,
                extractor=ClaimExtractionService(settings=self._settings),
            ).from_claims(scene.search_queries)

        outcome, related = await asyncio.gather(check_claims(), search_scene())
        if outcome is not None:
            report = self._filed(reading, outcome, ())
            report = replace(
                report,
                annotations=claim_annotations(outcome),
                exhibits=evidence_exhibits(outcome, self._settings.EVIDENCE_TOP_K),
            )
        else:
            report = self._unread(reading)
            report = replace(
                report,
                verdict=Verdict(
                    determination=Determination.INSUFFICIENT,
                    headline="Image inspected; authenticity remains unverified",
                    rationale=(
                        "The visible scene and available web matches are "
                        "recorded below. Add the claimed event, place or date "
                        "to check its context. A photograph alone does not "
                        "establish those facts."
                    ),
                    confidence=0,
                ),
            )
        exhibits = list(report.exhibits)
        for match in matches:
            exhibits.append(replace(match, ref=len(exhibits) + 1))
        seen = {e.url for e in exhibits}
        if related is not None:
            for claim in related.claims:
                for source in claim.sources[:5]:
                    if source.url in seen:
                        continue
                    seen.add(source.url)
                    exhibits.append(
                        Exhibit(
                            ref=len(exhibits) + 1,
                            source=source.title or source.domain,
                            url=source.url,
                            published=source.published_at.strftime("%d %b %Y")
                            if source.published_at
                            else "date not stated",
                            relevance=Relevance.LOW,
                            reliability=Reliability.LOW,
                            determination=Determination.REQUIRES_VERIFICATION,
                            extract="Related web result (not a confirmed image match): "
                            + (
                                source.retrievals[0].snippet
                                if source.retrievals
                                else source.title
                            ),
                        )
                    )
            if not related.searched:
                limitations.append(
                    "Scene web search did not complete: no search provider answered."
                )
        return replace(
            report,
            exhibits=tuple(exhibits),
            ledger=(
                *report.ledger,
                LedgerEntry("Reverse-image lookup", web_status),
                LedgerEntry("Image matches", str(len(matches))),
                LedgerEntry("Web sources", str(len(exhibits))),
            ),
            detail=ImageDetail(
                width=prepared.width,
                height=prepared.height,
                text=reading.text,
                regions=report.detail.regions if report.detail else (),
                description=scene.description if scene else "",
                observations=tuple(scene.observations) if scene else (),
                metadata=prepared.metadata,
                provenance=(
                    f"{len(matches)} matching web page(s) found. Original "
                    "capture date, publisher and authenticity are not established."
                )
                if matches
                else (
                    "No verified origin was established. "
                    "This is not evidence that the image is fake."
                ),
                web_status=web_status,
                limitations=tuple(limitations),
            ),
        )

    async def _fetch(self, artifact: Artifact) -> bytes:
        if not artifact.url:
            raise ValidationError(
                "An image artifact needs a URL to fetch.",
                details={"desk": str(self.desk)},
            )
        if fetch.is_managed_upload_url(
            artifact.url, public_api_url=self._settings.PUBLIC_API_URL
        ):
            from pathlib import Path
            from urllib.parse import urlsplit

            path = (
                Path(self._settings.UPLOAD_DIRECTORY)
                / urlsplit(artifact.url).path.rsplit("/", 1)[-1]
            )

            def read_upload() -> bytes:
                try:
                    with path.open("rb") as stream:
                        data = stream.read(self._settings.MAX_UPLOAD_BYTES + 1)
                except OSError as exc:
                    raise ValidationError(
                        "The uploaded image has expired or is no longer available. "
                        "Upload it again."
                    ) from exc
                if len(data) > self._settings.MAX_UPLOAD_BYTES:
                    raise ValidationError("The uploaded image is too large.")
                return data

            return await anyio.to_thread.run_sync(read_upload)
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

    def _ocr_unavailable(self) -> DeskReport:
        """Returns a graceful error report when OCR is not installed."""
        return DeskReport(
            desk=self.desk,
            verdict=Verdict(
                determination=Determination.INSUFFICIENT,
                headline="OCR Unavailable",
                rationale=(
                    "System dependencies for OCR (Tesseract) are not installed. "
                    "Cannot process image."
                ),
                confidence=0.0,
            ),
            ledger=(LedgerEntry("OCR", "Unavailable"),),
            signals=(),
            detail=ImageDetail(width=0, height=0, text="", regions=()),
        )

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
            exhibits=_outcome_exhibits(outcome, self._settings.EVIDENCE_TOP_K),
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
            LedgerEntry("Words read", str(len(reading.text.split()))),
            LedgerEntry(
                "Read confidence",
                "Not measured"
                if reading.variant == "vision model"
                else f"{round(reading.confidence * 100)}%",
            ),
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
        signals = (
            [] if reading.variant == "vision model" else [self._recovered(reading)]
        )
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
            _region(found.box, reading, 0, f"{found.label} {found.confidence:.0%}")
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


def _outcome_exhibits(outcome: Outcome, limit: int) -> tuple[Exhibit, ...]:
    from app.desks.factcheck import evidence_exhibits

    return evidence_exhibits(outcome, limit)


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
