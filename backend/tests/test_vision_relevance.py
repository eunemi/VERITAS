"""The gate that decides whether object detection runs, and on what.

Pure Python, so this is the one part of the vision package that can be exercised
in full with nothing installed. It is also where the interesting judgement lives:
what the gate *refuses* to route matters more than what it routes.
"""

from __future__ import annotations

from app.vision.relevance import COCO_LABELS, SYNONYMS, wanted


def test_text_about_no_object_asks_for_no_detector() -> None:
    """The common case, and the one that keeps torch off the critical path."""
    assert wanted("The central bank held the rate at 5.25% in March.") == frozenset()


def test_a_named_object_is_routed_to_its_label() -> None:
    assert "person" in wanted("A crowd gathered outside the courthouse.")
    assert "airplane" in wanted("The aircraft landed at 4pm.")


def test_a_two_word_label_beats_its_last_word() -> None:
    """The label is "cell phone"; "phone" is a synonym that resolves to it."""
    assert wanted("He was holding a cell phone.") == frozenset({"cell phone"})
    assert wanted("He was holding a phone.") == frozenset({"cell phone"})


def test_plurals_resolve_without_losing_the_natively_plural_labels() -> None:
    """Both spellings of the phrase are tried, which is why "skis" survives.

    Singularising unconditionally would turn ``skis`` into ``ski``, which is not a
    COCO class, and the gate would then refuse an image the detector can read.
    """
    assert wanted("Two people carrying skis.") == frozenset({"person", "skis"})
    assert wanted("A pile of sports balls.") == frozenset({"sports ball"})
    assert wanted("A pair of scissors.") == frozenset({"scissors"})


def test_an_object_the_detector_cannot_see_is_not_substituted() -> None:
    """The constraint that makes this gate honest rather than merely cheap.

    A tank is not in the vocabulary. Answering "the photo shows a tank" with the
    ``truck`` a detector would report is worse than reporting nothing, because it
    presents a detection of a different object as bearing on the claim.
    """
    assert wanted("The photo shows a tank in the square.") == frozenset()
    assert "truck" not in wanted("A tank rolled past.")


def test_every_synonym_lands_on_a_real_label() -> None:
    """A typo in the synonym table would silently ask for a class YOLO never emits."""
    unknown = sorted(v for v in SYNONYMS.values() if v not in COCO_LABELS)

    assert not unknown, f"synonyms map to non-COCO labels: {unknown}"


def test_no_synonym_shadows_a_label() -> None:
    """A key that is itself a label would be dead code, and confusing to read."""
    assert not sorted(set(SYNONYMS) & COCO_LABELS)


def test_the_vocabulary_is_the_released_weights() -> None:
    """80 classes. A short count means a label was dropped in transcription."""
    assert len(COCO_LABELS) == 80
    assert all(label == label.lower() for label in COCO_LABELS)
    assert max(len(label.split()) for label in COCO_LABELS) == 2


def test_matching_ignores_case_and_punctuation() -> None:
    """OCR output is not tidy prose: it arrives shouting, hyphenated and boxed in."""
    assert wanted("A CROWD outside.") == frozenset({"person"})
    assert wanted("| TELEVISION | 8pm |") == frozenset({"tv"})
