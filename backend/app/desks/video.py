from __future__ import annotations

import tempfile
import os
import cv2
import anyio.to_thread
import logging

from app.core.config import Settings, get_settings
from app.core.errors import ValidationError, ConfigurationError
from app.desks.image import ImageDesk
from app.domain import Artifact, Desk, DeskReport, ArtifactKind
from app.media import fetch
from app.vision import get_image_reader

logger = logging.getLogger(__name__)

class VideoDesk(ImageDesk):
    desk = Desk.VIDEO

    async def examine(
        self, artifact: Artifact, *, verification_id: str | None = None
    ) -> DeskReport:
        if not artifact.url:
            raise ValidationError(
                "A video artifact needs a URL to fetch.",
                details={"desk": str(self.desk)},
            )
            
        data = await fetch.fetch(
            artifact.url,
            timeout=self._settings.MEDIA_FETCH_TIMEOUT_SECONDS,
            limit=self._settings.MAX_UPLOAD_BYTES,
            accept=("video/",),
            allow_private=self._settings.MEDIA_ALLOW_PRIVATE_HOSTS,
        )

        def extract_middle_frame(video_bytes: bytes) -> bytes | None:
            fd, path = tempfile.mkstemp(suffix=".mp4")
            try:
                with os.fdopen(fd, 'wb') as f:
                    f.write(video_bytes)
                cap = cv2.VideoCapture(path)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if total_frames > 0:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total_frames // 2))
                ret, frame = cap.read()
                if ret:
                    ret_encode, buf = cv2.imencode('.jpg', frame)
                    if ret_encode:
                        return buf.tobytes()
                return None
            finally:
                if os.path.exists(path):
                    os.remove(path)

        frame_bytes = await anyio.to_thread.run_sync(extract_middle_frame, data)
        if not frame_bytes:
            raise ValidationError(
                "Could not extract a frame from the video.",
                details={"desk": str(self.desk)},
            )
            
        try:
            reading = await get_image_reader(self._settings).read(frame_bytes)
        except ConfigurationError as exc:
            logger.warning("Video desk missing OCR dependencies: %s", exc)
            rep = self._ocr_unavailable()
            # Update desk
            return DeskReport(
                desk=self.desk,
                verdict=rep.verdict,
                ledger=rep.ledger,
                annotations=rep.annotations,
                signals=rep.signals,
                exhibits=rep.exhibits,
                detail=rep.detail
            )

        if len(reading.text.strip()) < self._settings.IMAGE_MIN_TEXT_CHARS:
            rep = self._unread(reading)
            return DeskReport(
                desk=self.desk,
                verdict=rep.verdict,
                ledger=rep.ledger,
                annotations=rep.annotations,
                signals=rep.signals,
                exhibits=rep.exhibits,
                detail=rep.detail
            )

        outcome = await self._graph().run(
            Artifact(kind=ArtifactKind.TEXT, content=reading.text)
        )
        detections = await self._look(frame_bytes, reading)
        rep = self._filed(reading, outcome, detections)
        return DeskReport(
            desk=self.desk,
            verdict=rep.verdict,
            ledger=rep.ledger,
            annotations=rep.annotations,
            signals=rep.signals,
            exhibits=rep.exhibits,
            detail=rep.detail
        )

def build(settings: Settings | None = None) -> VideoDesk:
    return VideoDesk(settings=settings or get_settings())
