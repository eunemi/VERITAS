"""The arithmetic that decides which transcribed words are believed.

Every function here is pure and needs nothing installed, which is deliberate: this
is where the anti-hallucination gate lives, and a rule that can only be exercised
with librosa, numpy and a Whisper checkpoint present is a rule that stops being
exercised. :func:`app.audio.analyse.measure` is the one exception and is skipped
where the library is absent.

The property worth stating plainly, because two other modules depend on it: an
utterance's own stripped text stays a verbatim substring of what :func:`compose`
returns. That is what lets the desk quote a segment in an annotation and have the
frontend's ``indexOf`` find it in the transcript it was given.
"""

from __future__ import annotations

import pytest

from app.audio.analyse import compose, confident, covered, envelope, measure, voiced
from app.audio.base import Span, Utterance


def said(text: str, start: float, end: float, *, conf: float = 0.9) -> Utterance:
    return Utterance(text=text, start=start, end=end, confidence=conf)


# ------------------------------------------------------------------- covered ----


def test_a_span_containing_the_whole_utterance_covers_all_of_it() -> None:
    assert covered(1.0, 2.0, [Span(0.0, 5.0)]) == pytest.approx(1.0)


def test_a_span_nowhere_near_the_utterance_covers_none_of_it() -> None:
    assert covered(10.0, 12.0, [Span(0.0, 5.0)]) == 0.0


def test_no_spans_at_all_covers_none_of_it() -> None:
    """The silent-recording case, which is the one that matters most."""
    assert covered(1.0, 2.0, []) == 0.0


def test_a_partial_overlap_is_reported_as_the_fraction_it_is() -> None:
    """Half the utterance is inside the span, so half of it is supported."""
    assert covered(0.0, 4.0, [Span(2.0, 6.0)]) == pytest.approx(0.5)


def test_several_spans_under_one_utterance_add_up() -> None:
    """A pause mid-sentence splits the waveform, not the utterance."""
    found = covered(0.0, 4.0, [Span(0.0, 1.0), Span(3.0, 4.0)])
    assert found == pytest.approx(0.5)


def test_overlapping_spans_cannot_push_coverage_past_one() -> None:
    """``split`` does not return overlapping intervals, but the clamp is cheap and
    a coverage of 1.4 would silently defeat any floor above it."""
    found = covered(0.0, 2.0, [Span(0.0, 2.0), Span(0.5, 1.5)])
    assert found == pytest.approx(1.0)


def test_an_utterance_with_no_duration_covers_nothing() -> None:
    """Guards the division. Whisper does emit zero-length segments."""
    assert covered(3.0, 3.0, [Span(0.0, 5.0)]) == 0.0
    assert covered(3.0, 2.0, [Span(0.0, 5.0)]) == 0.0


# -------------------------------------------------------------------- voiced ----


def test_speech_the_waveform_supports_survives() -> None:
    utterances = (said("The rate was held.", 1.0, 3.0),)
    assert voiced(utterances, [Span(0.5, 4.0)], floor=0.35) == utterances


def test_speech_over_silence_is_dropped() -> None:
    """The gate, in one assertion.

    A decoder handed room tone emits its most likely continuation — reliably a
    fluent sentence nobody said. Left in, it is extracted as a claim, researched,
    and published with a determination against it.
    """
    kept = said("The rate was held.", 1.0, 3.0)
    invented = said("Subtitles by the Amara community.", 20.0, 23.0)

    assert voiced((kept, invented), [Span(0.5, 4.0)], floor=0.35) == (kept,)


def test_a_segment_opening_on_the_breath_before_the_first_word_survives() -> None:
    """Why the floor is a fraction rather than "all of it".

    The decoder's boundaries run a few hundred milliseconds loose at either end, and
    a segment legitimately starts before the sound does. Requiring full coverage
    would discard real speech on every recording.
    """
    utterance = said("The rate was held.", 0.0, 3.0)
    assert voiced((utterance,), [Span(1.0, 3.0)], floor=0.35) == (utterance,)


def test_the_floor_is_what_decides_a_marginal_segment() -> None:
    utterance = said("Possibly.", 0.0, 4.0)
    spans = [Span(3.0, 4.0)]

    assert voiced((utterance,), spans, floor=0.2) == (utterance,)
    assert voiced((utterance,), spans, floor=0.5) == ()


def test_coverage_exactly_at_the_floor_survives() -> None:
    """A boundary worth pinning: the comparison is ``>=``, so a segment measured at
    precisely the configured floor is kept rather than discarded."""
    utterance = said("Half heard.", 0.0, 4.0)
    assert voiced((utterance,), [Span(2.0, 4.0)], floor=0.5) == (utterance,)


def test_order_is_preserved() -> None:
    """:func:`compose` joins in sequence, so a reordering here would rewrite the
    transcript into something nobody said in that order."""
    first = said("The bank met on Tuesday.", 0.5, 2.0)
    second = said("It held the rate.", 2.2, 3.5)

    assert voiced((first, second), [Span(0.0, 4.0)], floor=0.35) == (first, second)


# ----------------------------------------------------------------- confident ----


def test_a_segment_the_decoder_doubted_is_dropped() -> None:
    sure = said("The rate was held.", 1.0, 3.0, conf=0.88)
    unsure = said("and nine percent besides", 3.0, 4.0, conf=0.09)

    assert confident((sure, unsure), floor=0.3) == (sure,)


def test_confidence_exactly_at_the_floor_survives() -> None:
    utterance = said("Marginal.", 1.0, 2.0, conf=0.3)
    assert confident((utterance,), floor=0.3) == (utterance,)


def test_a_floor_of_zero_keeps_everything() -> None:
    """So the confidence half of the gate can be turned off by configuration, and
    the waveform half is still in force independently."""
    utterances = (said("Anything.", 1.0, 2.0, conf=0.0),)
    assert confident(utterances, floor=0.0) == utterances


# ------------------------------------------------------------------- compose ----


def test_each_utterance_stays_a_verbatim_substring() -> None:
    """The invariant :mod:`app.desks.anchors` and the frontend both rely on.

    The frontend does ``copy.indexOf(annotation.quote)`` and silently drops a miss,
    so a transcript assembled in a way that alters an utterance's own characters
    would make every marker on the recording fail to render.
    """
    utterances = (
        said("The central bank held the rate", 0.4, 3.1),
        said("at 5.25%.", 3.2, 5.0),
    )
    text = compose(utterances)

    assert text == "The central bank held the rate at 5.25%."
    for utterance in utterances:
        assert utterance.text.strip() in text


def test_whisper_leading_spaces_do_not_double_up() -> None:
    """Whisper prefixes almost every segment with a space, so this is the normal
    case rather than an edge one."""
    assert compose((said(" Two words.", 0.0, 1.0), said(" And more.", 1.0, 2.0))) == (
        "Two words. And more."
    )


def test_an_empty_segment_contributes_nothing() -> None:
    composed = compose((said("Spoken.", 0.0, 1.0), said("   ", 1.0, 2.0)))
    assert composed == "Spoken."


def test_nothing_heard_composes_to_an_empty_string() -> None:
    """Which is what the desk's text floor then reads as an insufficiency."""
    assert compose(()) == ""


# ------------------------------------------------------------------ envelope ----


def test_the_envelope_has_one_value_per_bucket() -> None:
    assert len(envelope([0.1] * 500, 32)) == 32


def test_fewer_frames_than_buckets_still_fills_every_bucket() -> None:
    """A very short clip must not produce a waveform the frontend cannot draw."""
    assert len(envelope([0.2, 0.4, 0.6], 8)) == 8


def test_the_loudest_bucket_reads_one() -> None:
    """Normalised against the clip's own peak: this describes relative shape, and
    absolute loudness is reported separately as a level in dBFS."""
    shape = envelope([0.0, 0.1, 0.5, 0.0], 4)
    assert max(shape) == pytest.approx(1.0)


def test_a_bucket_takes_its_peak_not_its_mean() -> None:
    """A mean over a long bucket flattens speech into a straight line, and the whole
    point of the shape is to show where the sound is.

    The four frames are chosen so the two methods disagree *after* normalisation:
    peaks give ``(1.0, 0.5)`` where means would give two equal buckets.
    """
    assert envelope([1.0, 0.0, 0.5, 0.5], 2) == (
        pytest.approx(1.0),
        pytest.approx(0.5),
    )


def test_silence_produces_a_flat_envelope_rather_than_a_division() -> None:
    assert envelope([0.0, 0.0, 0.0], 3) == (0.0, 0.0, 0.0)


def test_no_buckets_and_no_frames_produce_nothing() -> None:
    assert envelope([0.1, 0.2], 0) == ()
    assert envelope([], 16) == ()


# ------------------------------------------------------------------- measure ----


async def test_measure_finds_the_sound_and_not_the_silence() -> None:
    """The one test here that runs librosa, and the only one that can be skipped.

    A second of silence, a second of tone, a second of silence. What is being
    checked is that the spans returned describe the middle — the property the gate
    above is built on — rather than any particular librosa call.
    """
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("librosa")
    from app.audio.base import Clip

    rate = 16_000
    times = numpy.arange(rate, dtype=numpy.float32) / rate
    tone = numpy.sin(2 * numpy.pi * 440 * times).astype(numpy.float32) * 0.5
    quiet = numpy.zeros(rate, dtype=numpy.float32)
    samples = numpy.concatenate([quiet, tone, quiet])

    acoustics = await measure(
        Clip(samples=samples, rate=rate), floor_db=35.0, buckets=64
    )

    assert acoustics.duration == pytest.approx(3.0, abs=0.05)
    assert acoustics.spans
    assert acoustics.spans[0].start == pytest.approx(1.0, abs=0.15)
    assert acoustics.spans[-1].end == pytest.approx(2.0, abs=0.15)
    assert acoustics.speech_seconds == pytest.approx(1.0, abs=0.3)
    assert len(acoustics.envelope) == 64
    assert acoustics.level_db < 0.0
