"""Tesseract, and the grouping of its word output back into readable text.

:func:`lines` and :func:`compose` are public and pure — they take the dictionary
``pytesseract.image_to_data`` returns and need no Tesseract installed — because the
part of this worth testing is the reassembly, not the recognition.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import anyio.to_thread

from app.core.config import Settings
from app.core.errors import ConfigurationError, PipelineError
from app.vision import prepare
from app.vision.base import Box, Reading, TextLine

#: ``(block, paragraph, line)``, Tesseract's own grouping of a word.
_Line = tuple[int, int, int]
#: ``(text, left, top, width, height, confidence)``.
_Word = tuple[str, int, int, int, int, float]


def lines(data: Mapping[str, Any], *, floor: float) -> tuple[TextLine, ...]:
    """Group Tesseract's per-word output into lines, dropping unsure words.

    Words are grouped on the ``(block_num, par_num, line_num)`` triple Tesseract
    itself assigns, rather than by clustering y-coordinates. Its layout analysis
    already knows that a two-column page has two columns; rebuilding that from
    geometry gets multi-column text and side captions wrong in ways that are hard
    to see and easy to ship.

    ``floor`` drops a word rather than reporting it, because a plausible misread
    inside a sentence is worse than a gap: "the rate was he1d at 5.25%" is a claim
    about something nobody said, and it will be checked as though it were.
    """
    texts = data.get("text") or []
    confidences = data.get("conf") or []
    grouped: dict[_Line, list[_Word]] = {}

    for index, raw in enumerate(texts):
        word = str(raw).strip()
        if not word:
            continue
        # Tesseract reports -1 for a box it found but did not classify.
        score = float(confidences[index]) / 100.0 if index < len(confidences) else 0.0
        if score < floor:
            continue
        key = (
            int(_at(data, "block_num", index)),
            int(_at(data, "par_num", index)),
            int(_at(data, "line_num", index)),
        )
        grouped.setdefault(key, []).append(
            (
                word,
                int(_at(data, "left", index)),
                int(_at(data, "top", index)),
                int(_at(data, "width", index)),
                int(_at(data, "height", index)),
                score,
            )
        )

    found: list[TextLine] = []
    for key in sorted(grouped):
        words = grouped[key]
        left = min(w[1] for w in words)
        top = min(w[2] for w in words)
        right = max(w[1] + w[3] for w in words)
        bottom = max(w[2] + w[4] for w in words)
        found.append(
            TextLine(
                text=" ".join(w[0] for w in words),
                box=Box(left, top, max(1, right - left), max(1, bottom - top)),
                confidence=sum(w[5] for w in words) / len(words),
                block=key[0],
            )
        )
    return tuple(found)


def compose(found: Sequence[TextLine]) -> str:
    """Join lines into text a claim extractor can read.

    Lines inside one block are joined with a *space*, and blocks are separated by
    a blank line. This is the decision that makes claim extraction work on an
    image at all: a line break in a picture is where the column ran out, not where
    the sentence ended, so preserving it hands the extractor a page of fragments
    and it finds no claims in any of them.
    """
    blocks: list[list[str]] = []
    current = -1
    for line in found:
        if line.block != current or not blocks:
            blocks.append([])
            current = line.block
        blocks[-1].append(line.text)
    return "\n\n".join(" ".join(block) for block in blocks if block)


def _at(data: Mapping[str, Any], field: str, index: int) -> Any:
    values = data.get(field) or []
    return values[index] if index < len(values) else 0


def _yield(reading: Reading) -> tuple[int, float]:
    """How much a pass recovered, for choosing between passes.

    Characters first, confidence as the tiebreak. Ranking on confidence alone
    prefers a pass that found three certain words and missed the paragraph.
    """
    return (len(reading.text), reading.confidence)


class TesseractReader:
    """Reads text with Tesseract, over several preparations of the image."""

    name = "tesseract"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def read(self, image: bytes) -> Reading:
        return await anyio.to_thread.run_sync(self._read, image)

    # -- everything below runs in a worker thread, never on the event loop --

    def _read(self, image: bytes) -> Reading:
        pytesseract, output = _pytesseract()
        config = f"--psm {self._settings.TESSERACT_PSM}"
        floor = self._settings.TESSERACT_MIN_CONFIDENCE

        readings: list[Reading] = []
        for candidate in prepare.candidates(
            image,
            upscale_to=self._settings.IMAGE_UPSCALE_TO,
            limit=self._settings.IMAGE_MAX_PASSES,
        ):
            data = self._data(pytesseract, output, candidate.image, config)
            found = tuple(
                TextLine(
                    text=line.text,
                    box=candidate.locate(line.box),
                    confidence=line.confidence,
                    block=line.block,
                )
                for line in lines(data, floor=floor)
            )
            readings.append(
                Reading(
                    text=compose(found),
                    lines=found,
                    width=candidate.origin[0],
                    height=candidate.origin[1],
                    confidence=(
                        sum(line.confidence for line in found) / len(found)
                        if found
                        else 0.0
                    ),
                    variant=candidate.name,
                    rotation=candidate.rotation,
                )
            )

        return max(readings, key=_yield)

    def _data(
        self, pytesseract: Any, output: Any, image: Any, config: str
    ) -> Mapping[str, Any]:
        """One recognition pass. A numpy frame goes in directly — no PIL needed."""
        try:
            result: Mapping[str, Any] = pytesseract.image_to_data(
                image,
                lang=self._settings.TESSERACT_LANGUAGE,
                config=config,
                output_type=output.DICT,
            )
        except pytesseract.TesseractNotFoundError as exc:
            raise ConfigurationError(
                "The Tesseract binary is not installed or not on PATH.",
                details={
                    "missing": "tesseract",
                    "install": "brew install tesseract (or: apt-get install "
                    "tesseract-ocr)",
                },
            ) from exc
        except pytesseract.TesseractError as exc:
            # A local tool that failed is not a bad gateway: nothing was called
            # over a network, so this is this deployment's problem to fix. The
            # usual cause is a language pack named in TESSERACT_LANGUAGE that was
            # never installed, which Tesseract reports on stderr and not as a
            # distinct exception type.
            raise PipelineError(
                "Tesseract could not read the image.",
                details={
                    "reason": str(exc).strip()[:200],
                    "language": self._settings.TESSERACT_LANGUAGE,
                },
            ) from exc
        return result


def _pytesseract() -> tuple[Any, Any]:
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:
        raise ConfigurationError(
            "pytesseract is required to read text from images.",
            details={"missing": "pytesseract", "install": "pip install pytesseract"},
        ) from exc
    return pytesseract, Output
