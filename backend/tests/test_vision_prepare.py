"""Image preparation: the coordinate arithmetic, and the OpenCV steps themselves.

Split in two on purpose, and the split is why ``importorskip`` is called inside
the tests that need it rather than at module scope. :func:`normalise_angle`,
:meth:`Box.within` and :meth:`Candidate.locate` are pure arithmetic, and they are
where a silent error lives — a region drawn in the wrong place looks like a bad
OCR result, not like a bug in a coordinate transform. Those run everywhere. The
tests that actually decode a PNG skip when OpenCV is absent.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.errors import PayloadTooLargeError, ValidationError
from app.vision import prepare
from app.vision.base import Box
from app.vision.prepare import (
    MAX_UPSCALE,
    Candidate,
    _upscale_factor,
    normalise_angle,
)


def opencv() -> tuple[Any, Any]:
    """OpenCV and NumPy, or skip. Called per test, not at import."""
    cv2 = pytest.importorskip("cv2", reason="OpenCV is not installed")
    numpy = pytest.importorskip("numpy", reason="NumPy is not installed")
    return cv2, numpy


def encode(width: int, height: int) -> bytes:
    """A PNG with a line of black text on white, the shape OCR expects."""
    cv2, numpy = opencv()
    frame = numpy.full((height, width, 3), 255, dtype=numpy.uint8)
    cv2.putText(
        frame,
        "RATE HELD",
        (10, height // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 0, 0),
        2,
    )
    ok, buffer = cv2.imencode(".png", frame)
    assert ok
    return bytes(buffer)


# ---------------------------------------------------------------- geometry ----


def test_a_box_is_reported_as_a_share_of_the_image() -> None:
    """Percentages, because the reader scales the image to fit its frame.

    A pixel offset would line up at exactly one zoom level.
    """
    assert Box(50, 100, 200, 40).within(1000, 800) == (5.0, 12.5, 20.0, 5.0)


def test_a_box_on_a_degenerate_image_reports_zeroes() -> None:
    """Rather than dividing by zero on a reading nothing was recovered from."""
    assert Box(0, 0, 10, 10).within(0, 0) == (0.0, 0.0, 0.0, 0.0)


def test_an_unmodified_candidate_returns_the_box_it_was_given() -> None:
    plain = Candidate("gray", None, 1.0, 0.0, (400, 300), (400, 300))

    assert plain.locate(Box(10, 20, 30, 40)) == Box(10, 20, 30, 40)


def test_a_box_found_on_an_upscaled_image_maps_back_down() -> None:
    scaled = Candidate("gray", None, 2.0, 0.0, (800, 600), (400, 300))

    assert scaled.locate(Box(100, 40, 200, 60)) == Box(50, 20, 100, 30)


def test_a_box_found_on_a_deskewed_image_moves_back_but_does_not_grow() -> None:
    """Rotation is undone on the centre only, and the size is left alone.

    Rotating a rectangle's corners and re-fitting an axis-aligned box around them
    inflates every side by the sine of the angle, describing a corner nothing is
    drawn at. For the few degrees deskew corrects, the centre is the whole of the
    error that matters.
    """
    turned = Candidate("deskewed", None, 1.0, 10.0, (400, 400), (400, 400))

    located = turned.locate(Box(100, 100, 120, 30))

    assert (located.w, located.h) == (120, 30)
    assert (located.x, located.y) != (100, 100)


def test_undoing_a_rotation_leaves_the_centre_of_rotation_alone() -> None:
    """A box centred on the pivot cannot move, whatever the angle."""
    for angle in (-12.0, -0.5, 3.0, 15.0):
        turned = Candidate("deskewed", None, 1.0, angle, (200, 200), (200, 200))

        assert turned.locate(Box(90, 90, 20, 20)) == Box(90, 90, 20, 20)


def test_a_box_is_clamped_to_the_original_image() -> None:
    """Deskew can push a box's centre past the edge, and a negative coordinate is
    not something the frontend can draw."""
    turned = Candidate("deskewed", None, 1.0, 15.0, (100, 100), (100, 100))

    located = turned.locate(Box(0, 95, 20, 5))

    assert located.x >= 0
    assert located.y >= 0
    assert located.w >= 1


# ------------------------------------------------------------------- angles ----


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # OpenCV before 4.5 returned [-90, 0) for the same rectangle 4.5 and later
        # return [0, 90) for. Both spellings of "two degrees off level" have to
        # fold to the same answer, or a wrapper written against one convention
        # rotates the page by ninety degrees on the other and then reports a
        # confident reading of nothing.
        (-88.0, 2.0),
        (2.0, 2.0),
        (-2.0, -2.0),
        (88.0, -2.0),
        (0.0, 0.0),
        (45.0, 45.0),
        (-45.0, 45.0),
        (90.0, 0.0),
        (-90.0, 0.0),
    ],
)
def test_both_opencv_conventions_fold_to_one_range(raw: float, expected: float) -> None:
    assert normalise_angle(raw) == pytest.approx(expected)


def test_every_angle_lands_inside_the_range() -> None:
    for raw in range(-180, 181):
        assert -45.0 < normalise_angle(float(raw)) <= 45.0


# ------------------------------------------------------------------ scaling ----


def test_a_small_image_is_enlarged_towards_the_target() -> None:
    """Tesseract's classifier wants about 30px of x-height and falls off below 20."""
    assert _upscale_factor(300, 900) == pytest.approx(3.0)


def test_a_large_image_is_never_reduced() -> None:
    """A big scan is already legible, and downsampling loses thin strokes first."""
    assert _upscale_factor(2000, 900) == 1.0
    assert _upscale_factor(900, 900) == 1.0


def test_enlargement_is_capped() -> None:
    """Interpolation invents no detail: a 22x blur reads worse than the original."""
    assert _upscale_factor(40, 900) == MAX_UPSCALE


def test_upscaling_off_is_upscaling_off() -> None:
    assert _upscale_factor(100, 0) == 1.0


# -------------------------------------------------------------- with opencv ----


def test_bytes_that_are_not_an_image_are_a_validation_error() -> None:
    opencv()

    with pytest.raises(ValidationError, match="could not be decoded"):
        prepare.decode(b"this is not a PNG")


def test_an_image_over_the_pixel_ceiling_is_refused() -> None:
    """The decompression-bomb guard.

    The ceiling is lowered rather than a 46-megapixel fixture encoded, because
    building one costs more than the whole rest of this file. What is being
    asserted is that the check fires and reports the dimensions, not the constant.
    """
    opencv()
    original = prepare.MAX_PIXELS
    prepare.MAX_PIXELS = 100
    try:
        with pytest.raises(PayloadTooLargeError, match="too large") as raised:
            prepare.decode(encode(60, 40))
    finally:
        prepare.MAX_PIXELS = original

    assert raised.value.details["width"] == 60
    assert raised.value.details["height"] == 40


def test_candidates_are_ordered_by_value_and_never_empty() -> None:
    found = prepare.candidates(encode(600, 200), upscale_to=0, limit=3)

    assert [c.name for c in found][:2] == ["gray", "threshold"]
    assert all(c.origin == (600, 200) for c in found)


def test_the_pass_limit_keeps_the_most_valuable_passes() -> None:
    """``limit=1`` reads the safest preparation, not an arbitrary one."""
    assert [c.name for c in prepare.candidates(encode(600, 200), limit=1)] == ["gray"]


def test_an_upscaled_candidate_records_the_scale_it_used() -> None:
    """Without which ``locate`` cannot map a box back to the submitted image."""
    found = prepare.candidates(encode(300, 100), upscale_to=400, limit=1)[0]

    assert found.scale == pytest.approx(4.0)
    assert found.size == (1200, 400)
    assert found.origin == (300, 100)


def test_a_level_page_is_not_rotated() -> None:
    """Deskewing an image with no skew resamples every pixel for nothing."""
    found = prepare.candidates(encode(600, 200), limit=3)

    assert all(c.rotation == 0.0 for c in found)


def test_a_prepared_image_keeps_the_dimensions_locate_assumes() -> None:
    """``rotate`` holds the output size constant so ``locate`` needs no translation."""
    found = prepare.candidates(encode(600, 200), limit=3)

    assert all((c.image.shape[1], c.image.shape[0]) == c.size for c in found)
