"""YOLOv8 object detection, run only when :mod:`app.vision.relevance` asks for it.

``ultralytics`` is imported inside function bodies and the weights are loaded once
per process behind a lock, for the reasons :mod:`app.nlp.resources` documents: the
dependency is large, the load is slow, and a deployment that never submits an image
about objects should not pay for either.
"""

from __future__ import annotations

import threading
from typing import Any

import anyio.to_thread

from app.core.config import Settings
from app.core.errors import ConfigurationError, PipelineError
from app.vision import prepare
from app.vision.base import Box, Detection

_LOAD_LOCK = threading.Lock()
#: Ultralytics keeps mutable predictor state on the model between calls, so two
#: threads sharing one loaded model interleave and one of them reads the other's
#: results. Loading is guarded to load once; predicting is guarded because the
#: object is not reentrant.
_PREDICT_LOCK = threading.Lock()
_MODELS: dict[str, Any] = {}


def load(weights: str) -> Any:
    """The model for ``weights``, loaded at most once per process."""
    model = _MODELS.get(weights)
    if model is not None:
        return model

    with _LOAD_LOCK:
        cached = _MODELS.get(weights)
        if cached is not None:
            return cached
        built = _build(weights)
        _MODELS[weights] = built
        return built


def _build(weights: str) -> Any:
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ConfigurationError(
            "ultralytics is required for object detection.",
            details={
                "missing": "ultralytics",
                "install": "pip install ultralytics",
                "disable": "set IMAGE_DETECTION_ENABLED=false",
            },
        ) from exc

    try:
        return YOLO(weights)
    except Exception as exc:
        # Deliberately broad. Ultralytics resolves a bare filename by downloading
        # it, so the failures here span its HTTP stack, torch's deserialiser and
        # the filesystem, and the exception types are not part of its public API.
        # Every one of them means the same thing to this desk.
        raise ConfigurationError(
            "The object detection weights could not be loaded.",
            details={
                "weights": weights,
                "reason": str(exc).strip()[:200],
                "hint": "A bare filename is downloaded on first use; set "
                "YOLO_WEIGHTS to a local path for a sealed deployment.",
            },
        ) from exc


class YoloDetector:
    """Finds COCO objects, filtered to the labels the caller asked about."""

    name = "yolo"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def detect(
        self, image: bytes, labels: frozenset[str]
    ) -> tuple[Detection, ...]:
        if not labels:
            return ()
        return await anyio.to_thread.run_sync(self._detect, image, labels)

    # -- everything below runs in a worker thread, never on the event loop --

    def _detect(self, image: bytes, labels: frozenset[str]) -> tuple[Detection, ...]:
        # BGR, straight from cv2, because that is what ultralytics documents for a
        # numpy input. Handing it RGB does not raise — it detects fewer objects at
        # lower confidence, which reads as a bad model rather than swapped
        # channels.
        frame = prepare.decode(image)
        model = load(self._settings.YOLO_WEIGHTS)

        try:
            with _PREDICT_LOCK:
                results = model.predict(
                    frame, conf=self._settings.YOLO_MIN_CONFIDENCE, verbose=False
                )
        except Exception as exc:
            raise PipelineError(
                "Object detection failed.",
                details={"reason": str(exc).strip()[:200]},
            ) from exc

        found = [d for result in results for d in _read(result, labels)]
        found.sort(key=lambda d: d.confidence, reverse=True)
        return tuple(found)


def _read(result: Any, labels: frozenset[str]) -> list[Detection]:
    names = getattr(result, "names", None) or {}
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return []

    found: list[Detection] = []
    for box in boxes:
        label = str(names.get(int(box.cls), "")).strip()
        if label not in labels:
            continue
        left, top, right, bottom = (float(v) for v in box.xyxy[0])
        found.append(
            Detection(
                label=label,
                confidence=min(1.0, max(0.0, float(box.conf))),
                box=Box(
                    x=round(left),
                    y=round(top),
                    w=max(1, round(right - left)),
                    h=max(1, round(bottom - top)),
                ),
            )
        )
    return found
