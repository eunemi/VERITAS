"""Image reading and object detection, behind two registries.

One enum keying two roles, exactly as :mod:`app.llm` does for generation and
embeddings: ``IMAGE_READER`` selects what recovers text, ``OBJECT_DETECTOR``
selects what finds objects. The concrete modules are imported here so their
``register`` calls run, which is what makes a setting reach an implementation.

Neither import costs anything at startup — ``cv2``, ``pytesseract`` and
``ultralytics`` are all imported inside function bodies, so this package loads on a
machine that has none of them and a missing one becomes a
:class:`app.core.errors.ConfigurationError` naming its install command.
"""

from __future__ import annotations

from app.core.config import Settings, VisionProvider
from app.core.registry import ProviderRegistry
from app.vision.base import Detection, ImageReader, ObjectDetector, Reading, TextLine
from app.vision.detect import YoloDetector
from app.vision.ocr import TesseractReader

readers: ProviderRegistry[VisionProvider, ImageReader] = ProviderRegistry(
    "image reader"
)
detectors: ProviderRegistry[VisionProvider, ObjectDetector] = ProviderRegistry(
    "object detector"
)

readers.register(VisionProvider.TESSERACT, TesseractReader)
detectors.register(VisionProvider.YOLO, YoloDetector)


def get_image_reader(settings: Settings) -> ImageReader:
    return readers.resolve(settings.IMAGE_READER, settings)


def get_object_detector(settings: Settings) -> ObjectDetector:
    return detectors.resolve(settings.OBJECT_DETECTOR, settings)


__all__ = [
    "Detection",
    "ImageReader",
    "ObjectDetector",
    "Reading",
    "TesseractReader",
    "TextLine",
    "YoloDetector",
    "detectors",
    "get_image_reader",
    "get_object_detector",
    "readers",
]
