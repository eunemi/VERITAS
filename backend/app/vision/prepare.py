"""Turning submitted bytes into images an OCR engine can actually read.

This is the OpenCV half of the desk and the one place in it where the comments
earn their keep, because most of what follows is a decision about a specific
failure mode rather than a step in an obvious sequence.

The organising idea: **preprocessing that rescues a photograph ruins a
screenshot.** Binarising a crisp PNG of white-on-dark text throws away antialiased
edges Tesseract was reading fine; deskewing a screenshot that has no skew rotates
it by whatever angle the noise suggested. So nothing here decides what an image
needs. :func:`candidates` produces several preparations of it, each is read, and
the reader keeps whichever recognised the most text. Arbitration by result, not by
guesswork about the input.

``cv2`` and ``numpy`` are imported inside function bodies, never at module scope,
so this module imports on a machine without them and a missing install is a
:class:`ConfigurationError` naming the fix.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.core.errors import (
    ConfigurationError,
    PayloadTooLargeError,
    ValidationError,
)
from app.vision.base import Box

#: Ceiling on decoded pixels, about a 46-megapixel image. A 4 KB PNG can declare
#: dimensions of 60,000 by 60,000 and cost 10 GB to decode, which is the standard
#: decompression bomb. See the note in :func:`decode` about what this does not do.
MAX_PIXELS = 46_000_000

#: Never enlarge by more than this. A 40-pixel-tall crop scaled to 900 is 22x, and
#: interpolation invents no detail: the result is a smooth blur that reads worse
#: than the original and costs 500 times the recognition time.
MAX_UPSCALE = 4.0

#: Below this the measured angle is noise, above it the measurement is wrong — see
#: :func:`skew`.
MIN_SKEW_DEGREES = 0.5
MAX_SKEW_DEGREES = 15.0


def _cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:
        raise ConfigurationError(
            "OpenCV is required to prepare images for reading.",
            details={
                "missing": "cv2",
                "install": "pip install opencv-python-headless",
            },
        ) from exc
    return cv2


def _numpy() -> Any:
    try:
        import numpy
    except ImportError as exc:
        raise ConfigurationError(
            "NumPy is required to prepare images for reading.",
            details={"missing": "numpy", "install": "pip install numpy"},
        ) from exc
    return numpy


def decode(data: bytes) -> Any:
    """Decode image bytes to a BGR frame.

    Note the ordering the pixel guard cannot escape: ``imdecode`` allocates the
    frame before there is anything to measure, so this rejects a decompression
    bomb *after* paying for it once. Refusing one before decoding means parsing
    each container's header here — a second, partial image library. The fetch-side
    byte ceiling is the real defence; this catches the small-file case and keeps
    one oversized image from being read for a minute.
    """
    numpy = _numpy()
    cv2 = _cv2()

    frame = cv2.imdecode(numpy.frombuffer(data, dtype=numpy.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValidationError(
            "The submitted file could not be decoded as an image.",
            details={"bytes": len(data)},
        )

    height, width = frame.shape[:2]
    if width * height > MAX_PIXELS:
        raise PayloadTooLargeError(
            "The image is too large to examine.",
            details={"width": width, "height": height, "limit": MAX_PIXELS},
        )
    return frame


@dataclass(frozen=True, slots=True)
class Candidate:
    """One preparation of an image, plus how to get back from it.

    ``scale`` and ``rotation`` are what was done, and :meth:`locate` undoes them.
    A box is only useful to a reader if it is expressed in the coordinates of the
    picture they are looking at, not of the intermediate this desk happened to
    read.
    """

    name: str
    image: Any
    scale: float
    rotation: float
    #: ``(width, height)`` of the candidate itself, for the rotation centre.
    size: tuple[int, int]
    #: ``(width, height)`` of the original.
    origin: tuple[int, int]

    def locate(self, box: Box) -> Box:
        """Map a box in this candidate's coordinates back to original pixels.

        Rotation is undone about the candidate's centre and applied to the box
        *centre only*, leaving the width and height as they were. That is
        deliberate: the boxes drawn from these are axis-aligned, and rotating a
        rectangle's corners then re-fitting an axis-aligned box around them
        inflates every side by the sine of the angle — describing a corner
        nothing is drawn at. For the few degrees deskew ever corrects, moving the
        centre is the whole of the error that matters.
        """
        cx = self.size[0] / 2
        cy = self.size[1] / 2
        x = box.x + box.w / 2
        y = box.y + box.h / 2

        if self.rotation:
            angle = math.radians(-self.rotation)
            dx = x - cx
            dy = y - cy
            x = cx + math.cos(angle) * dx + math.sin(angle) * dy
            y = cy - math.sin(angle) * dx + math.cos(angle) * dy

        scale = self.scale or 1.0
        w = box.w / scale
        h = box.h / scale
        left = x / scale - w / 2
        top = y / scale - h / 2

        width, height = self.origin
        return Box(
            x=max(0, min(width, round(left))),
            y=max(0, min(height, round(top))),
            w=max(1, min(width, round(w))),
            h=max(1, min(height, round(h))),
        )


def normalise_angle(angle: float) -> float:
    """Fold a ``minAreaRect`` angle into the (-45, 45] range.

    The one piece of arithmetic here that is a compatibility shim rather than
    image processing. OpenCV changed this return value in 4.5: before, the angle
    was in [-90, 0); from 4.5 it is in [0, 90). A wrapper written against one
    convention and run against the other rotates the page by ninety degrees and
    then reports a confident reading of nothing at all. Folding both into the same
    small range is correct under either, because a rectangle's orientation is only
    defined modulo 90 degrees anyway.
    """
    angle = angle % 90.0
    if angle > 45.0:
        angle -= 90.0
    return angle


def skew(gray: Any) -> float:
    """Degrees the text on ``gray`` appears rotated by, or 0.0 to leave it alone.

    Measured from the minimum-area rectangle around the dark pixels, which is
    cheap and, for a page of text, closely tracks the baseline angle.

    It has one loud failure: on an image whose dark pixels are a *picture* rather
    than text, the rectangle fits the subject and the angle is meaningless. That
    case is not distinguishable from a genuinely skewed page by looking at the
    number alone, so it is bounded instead — an angle over
    ``MAX_SKEW_DEGREES`` is treated as a bad measurement rather than a steeply
    tilted page, because a document photographed at more than about fifteen
    degrees is rare and a mismeasurement is not. Under ``MIN_SKEW_DEGREES`` there
    is nothing to win, and rotating resamples every pixel for no gain.
    """
    cv2 = _cv2()

    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    points = cv2.findNonZero(mask)
    if points is None or len(points) < 2:
        return 0.0

    angle = normalise_angle(float(cv2.minAreaRect(points)[-1]))
    if MIN_SKEW_DEGREES <= abs(angle) <= MAX_SKEW_DEGREES:
        return angle
    return 0.0


def rotate(image: Any, angle: float) -> Any:
    """Rotate about the centre, keeping the output the same size as the input.

    Two choices worth naming. ``BORDER_REPLICATE``, because the default black fill
    leaves a dark wedge in each corner and Otsu — which is looking for two
    brightness populations — reads those wedges as ink and shifts its threshold to
    accommodate them. And the size is held constant rather than expanded to fit
    the rotated bounds, so that a box found here maps back through
    :meth:`Candidate.locate` with one rotation and no translation term.
    """
    cv2 = _cv2()
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def binarise(gray: Any) -> Any:
    """Otsu threshold, after a light blur.

    The blur is the part that is not obvious. Otsu picks its threshold from the
    histogram's two modes, and JPEG ringing around glyph edges adds a third
    population of mid-grey pixels that drags the threshold towards the ink and
    thins the strokes. A 3x3 Gaussian removes it; 5x5 also closes the counters of
    8-10 pixel type, which turns every ``e`` into a ``c``.

    Adaptive thresholding is the usual alternative and is not used: it is better
    on uneven lighting, but its block size has to be tuned to the glyph height,
    which is not known until something has read the page.
    """
    cv2 = _cv2()
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, out = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return out


def _upscale_factor(height: int, target: int) -> float:
    """How much to enlarge a ``height``-pixel image, upwards only.

    Tesseract's classifier expects roughly 30 pixels of x-height and degrades
    steeply below about 20, so small images are enlarged before reading rather
    than after failing. Never *reduced*: a large scan is already legible, and
    downsampling to save time loses the thin strokes first.
    """
    if target <= 0 or height <= 0 or height >= target:
        return 1.0
    return min(MAX_UPSCALE, target / height)


def candidates(
    data: bytes, *, upscale_to: int = 0, limit: int = 3
) -> tuple[Candidate, ...]:
    """Preparations of ``data`` to read, best-value first.

    Ordered grayscale, thresholded, deskewed, so ``limit=1`` reads the safest pass
    and ``limit=2`` adds the one that helps most often. Always returns at least
    one candidate.
    """
    cv2 = _cv2()

    frame = decode(data)
    height, width = frame.shape[:2]
    origin = (width, height)

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    scale = _upscale_factor(height, upscale_to)
    if scale > 1.0:
        gray = cv2.resize(
            gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
        )

    size = (gray.shape[1], gray.shape[0])
    found = [
        Candidate("gray", gray, scale, 0.0, size, origin),
        Candidate("threshold", binarise(gray), scale, 0.0, size, origin),
    ]

    angle = skew(gray)
    if angle:
        turned = binarise(rotate(gray, angle))
        found.append(Candidate("deskewed", turned, scale, angle, size, origin))

    return tuple(found[: max(1, limit)])
