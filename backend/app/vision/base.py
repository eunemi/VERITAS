"""What an image reader and an object detector return, and their contracts.

Plain Python: no OpenCV, no Tesseract, no torch. The types the image desk reads
are defined here so that the desk, the schemas and the tests can all be exercised
on a machine that has none of those installed.

Coordinates are in pixels of the *original* submitted image. The mapping back from
whatever preprocessed variant actually produced a reading is
:meth:`app.vision.prepare.Candidate.locate`'s job, and it is done before any box
reaches these types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class Box:
    """An axis-aligned rectangle in pixels, measured from the top left."""

    x: int
    y: int
    w: int
    h: int

    def within(self, width: int, height: int) -> tuple[float, float, float, float]:
        """This box as percentages of a ``width`` by ``height`` image.

        The form :class:`app.domain.PlateRegion` wants, because the reader that
        draws these scales the image to fit its frame.
        """
        if width <= 0 or height <= 0:
            return (0.0, 0.0, 0.0, 0.0)
        return (
            100.0 * self.x / width,
            100.0 * self.y / height,
            100.0 * self.w / width,
            100.0 * self.h / height,
        )


@dataclass(frozen=True, slots=True)
class TextLine:
    """One line of recognised text and where on the page it sat.

    ``block`` is the reader's own layout grouping — a column, a caption, a chyron.
    It is carried rather than discarded because joining lines across a block
    boundary is what turns two unrelated captions into one sentence.
    """

    text: str
    box: Box
    confidence: float
    block: int = 0


@dataclass(frozen=True, slots=True)
class Reading:
    """Everything one OCR pass recovered from an image.

    ``variant`` and ``rotation`` name the preprocessing that produced this, which
    is what makes an unexpectedly poor reading diagnosable from a stored record
    rather than only by re-running with the image in hand.
    """

    text: str
    lines: tuple[TextLine, ...]
    width: int
    height: int
    confidence: float
    variant: str = "original"
    rotation: float = 0.0

    @property
    def words(self) -> int:
        return sum(len(line.text.split()) for line in self.lines)


@dataclass(frozen=True, slots=True)
class Detection:
    """One object a detector found, at ``box`` in the original image."""

    label: str
    confidence: float
    box: Box


@runtime_checkable
class ImageReader(Protocol):
    """Recovers text from image bytes.

    Implementations raise from :mod:`app.core.errors` on failure — never a
    library-specific exception. A caller of this protocol has no way to import
    ``pytesseract.TesseractError`` to catch it, and should not have to.
    """

    name: str

    async def read(self, image: bytes) -> Reading: ...


@runtime_checkable
class ObjectDetector(Protocol):
    """Finds objects in image bytes, restricted to ``labels``.

    ``labels`` is required rather than optional: this runs only when something in
    the image's text asked about a specific object, and a detector free to report
    everything it sees would fill a record with furniture.
    """

    name: str

    async def detect(
        self, image: bytes, labels: frozenset[str]
    ) -> tuple[Detection, ...]: ...
