"""Reassembling Tesseract's word-level output into text worth checking.

:func:`lines` and :func:`compose` take the dictionary
``pytesseract.image_to_data(..., output_type=Output.DICT)`` returns, so both are
driven here from recorded payloads with no Tesseract installed. That is deliberate:
the recognition is the library's problem, and the grouping — which is this
codebase's problem, and the part that decides whether a claim extractor sees a
sentence or a pile of fragments — is what these assertions pin.

The payload shape is Tesseract's own: parallel lists, one entry per box, with
``level`` 5 rows carrying words and the lower levels carrying the layout boxes
that contain them. The lower-level rows are included in the fixtures because they
are present in the real output and are what an implementation reading ``text``
naively would trip over.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.vision.base import Box, Reading, TextLine
from app.vision.ocr import _yield, compose, lines

#: ``(text, conf, block, par, line, left, top, width, height)`` — the nine columns
#: of Tesseract's output that :func:`lines` reads.
Row = tuple[str, int, int, int, int, int, int, int, int]


def payload(*rows: Row) -> dict[str, Any]:
    """Build an ``image_to_data`` dict from :data:`Row` tuples."""
    fields = ("text", "conf", "block_num", "par_num", "line_num")
    boxes = ("left", "top", "width", "height")
    data: dict[str, Any] = {name: [] for name in (*fields, *boxes)}
    data["level"] = []
    for row in rows:
        for name, value in zip((*fields, *boxes), row, strict=True):
            data[name].append(value)
        data["level"].append(5)
    return data


#: One headline over two physical lines, then a separate caption. The shape a
#: screenshot of a news page actually produces.
PAGE = payload(
    ("The", 96, 1, 1, 1, 40, 20, 60, 24),
    ("central", 94, 1, 1, 1, 110, 20, 130, 24),
    ("bank", 91, 1, 1, 1, 250, 20, 90, 24),
    ("held", 95, 1, 1, 2, 40, 54, 80, 24),
    ("the", 97, 1, 1, 2, 130, 54, 60, 24),
    ("rate", 93, 1, 1, 2, 200, 54, 80, 24),
    ("at", 99, 1, 1, 2, 290, 54, 40, 24),
    ("5.25%.", 88, 1, 1, 2, 340, 54, 120, 24),
    ("Photograph:", 72, 2, 1, 1, 40, 400, 190, 18),
    ("Reuters", 70, 2, 1, 1, 240, 400, 120, 18),
)


def test_words_are_grouped_into_the_lines_tesseract_assigned() -> None:
    found = lines(PAGE, floor=0.0)

    assert [line.text for line in found] == [
        "The central bank",
        "held the rate at 5.25%.",
        "Photograph: Reuters",
    ]


def test_a_line_box_encloses_every_word_in_it() -> None:
    """The box is what a region is drawn from, so it has to bound the whole line."""
    first = lines(PAGE, floor=0.0)[0]

    assert first.box == Box(x=40, y=20, w=300, h=24)


def test_a_line_carries_the_mean_confidence_of_its_words() -> None:
    caption = lines(PAGE, floor=0.0)[2]

    assert caption.confidence == pytest.approx(0.71)
    assert caption.block == 2


def test_unsure_words_are_dropped_rather_than_reported() -> None:
    """A plausible misread inside a sentence is worse than a gap.

    "the rate was he1d at 5.25%" reads as a claim about something nobody said, and
    it is checked as though it were — so a word the recogniser is unsure of does
    not survive to the pipeline at all.
    """
    doubtful = payload(
        ("the", 96, 1, 1, 1, 0, 0, 30, 10),
        ("rate", 95, 1, 1, 1, 40, 0, 40, 10),
        ("was", 94, 1, 1, 1, 90, 0, 30, 10),
        ("he1d", 22, 1, 1, 1, 130, 0, 40, 10),
    )

    assert [line.text for line in lines(doubtful, floor=0.45)] == ["the rate was"]


def test_a_box_tesseract_found_but_never_classified_is_dropped() -> None:
    """Tesseract reports ``-1`` for those, which no floor above zero admits."""
    unclassified = payload(
        ("", -1, 1, 1, 1, 0, 0, 30, 10),
        ("Rate", 92, 1, 1, 1, 40, 0, 40, 10),
    )

    assert [line.text for line in lines(unclassified, floor=0.45)] == ["Rate"]


def test_a_line_emptied_by_the_floor_leaves_no_empty_line_behind() -> None:
    thin = payload(
        ("Headline", 95, 1, 1, 1, 0, 0, 80, 20),
        ("blurry", 10, 1, 1, 2, 0, 30, 60, 20),
    )

    assert [line.text for line in lines(thin, floor=0.45)] == ["Headline"]


def test_a_payload_with_no_words_reads_as_nothing() -> None:
    assert lines({}, floor=0.45) == ()
    assert compose(()) == ""


# ------------------------------------------------------------------ compose ----


def test_lines_within_a_block_are_joined_into_a_sentence() -> None:
    """The decision that makes claim extraction work on an image at all.

    A line break in a picture is where the column ran out, not where the sentence
    ended. Preserving it hands the extractor "The central bank" and "held the rate
    at 5.25%." as two fragments, and it finds no checkable claim in either.
    """
    assert compose(lines(PAGE, floor=0.0)).startswith(
        "The central bank held the rate at 5.25%."
    )


def test_separate_blocks_stay_separate() -> None:
    """A caption is not the continuation of the headline above it."""
    text = compose(lines(PAGE, floor=0.0))

    assert text == ("The central bank held the rate at 5.25%.\n\nPhotograph: Reuters")


def test_a_block_that_recurs_after_another_is_not_merged_backwards() -> None:
    """Grouping follows the reading order, not the block number.

    Interleaved blocks happen on a multi-column page. Collapsing by block id would
    reorder the page; keeping runs preserves what was read where.
    """
    found = (
        TextLine("Column one", Box(0, 0, 10, 10), 0.9, block=1),
        TextLine("Column two", Box(0, 20, 10, 10), 0.9, block=2),
        TextLine("continues here", Box(0, 40, 10, 10), 0.9, block=1),
    )

    assert compose(found) == "Column one\n\nColumn two\n\ncontinues here"


# ------------------------------------------------------------ pass selection ----


def reading(text: str, confidence: float) -> Reading:
    return Reading(
        text=text,
        lines=(TextLine(text, Box(0, 0, 1, 1), confidence),),
        width=100,
        height=100,
        confidence=confidence,
    )


def test_the_pass_that_recovered_more_text_wins() -> None:
    """Ranking on confidence alone prefers three certain words to the paragraph."""
    certain = reading("Rate held", 0.99)
    fuller = reading("The central bank held the rate at 5.25% in March.", 0.83)

    assert max((certain, fuller), key=_yield) is fuller


def test_confidence_breaks_a_tie_between_equal_readings() -> None:
    clean = reading("Rate held at 5.25%", 0.94)
    murky = reading("Rate he1d at 5.25%", 0.61)

    assert max((murky, clean), key=_yield) is clean
