"""Measuring the signal, and using it to decide which words to believe.

Two halves. The bottom is librosa: the loud stretches, a drawable envelope, a mean
level. The top is arithmetic over those numbers, and it is the part that matters —
a speech recogniser handed silence does not return nothing, it returns its most
likely continuation, which is why a stretch of room tone so reliably transcribes as
a channel sign-off or a subtitling credit. Those sentences are grammatical, fluent,
and were never said.

:func:`voiced` is the gate. An utterance is kept only if the acoustic measurement
independently agrees there was sound under it. Nothing downstream — no claim
extraction, no verdict — sees a segment that failed here.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import anyio.to_thread

from app.audio.base import Acoustics, Clip, Span, Utterance
from app.core.errors import ConfigurationError, PipelineError


def covered(start: float, end: float, spans: Sequence[Span]) -> float:
    """What fraction of ``start``–``end`` overlaps ``spans``, 0–1."""
    width = end - start
    if width <= 0:
        return 0.0
    overlap = sum(
        max(0.0, min(end, span.end) - max(start, span.start)) for span in spans
    )
    return min(1.0, overlap / width)


def voiced(
    utterances: Sequence[Utterance], spans: Sequence[Span], *, floor: float
) -> tuple[Utterance, ...]:
    """Keep only utterances the waveform agrees were spoken.

    ``floor`` is the fraction of an utterance's own duration that must fall inside a
    non-silent span. Not all of it, because the decoder's boundaries are a few
    hundred milliseconds loose at either end and a segment legitimately opens on the
    breath before the first word; but enough that a sentence sitting over nothing
    cannot survive.
    """
    return tuple(u for u in utterances if covered(u.start, u.end, spans) >= floor)


def confident(
    utterances: Sequence[Utterance], *, floor: float
) -> tuple[Utterance, ...]:
    return tuple(u for u in utterances if u.confidence >= floor)


def compose(utterances: Sequence[Utterance]) -> str:
    """Join utterances into the text sent for claim extraction.

    Each utterance's own stripped text stays a verbatim substring of the result,
    which is what lets the desk quote a segment in an annotation and have the
    frontend find it in the transcript it was given.
    """
    return " ".join(u.text.strip() for u in utterances if u.text.strip())


def envelope(levels: Sequence[float], buckets: int) -> tuple[float, ...]:
    """Reduce per-frame levels to ``buckets`` peaks, each 0–1.

    Peak rather than mean per bucket, because a mean over a long bucket flattens
    speech into a straight line and the point of the shape is to show where sound
    is. Normalised against the loudest bucket, so this describes relative shape
    only; absolute loudness is :attr:`Acoustics.level_db`.
    """
    if buckets <= 0 or not levels:
        return ()

    peaks = []
    for index in range(buckets):
        low = (index * len(levels)) // buckets
        high = max(low + 1, ((index + 1) * len(levels)) // buckets)
        peaks.append(max(levels[low:high], default=0.0))

    ceiling = max(peaks)
    if ceiling <= 0:
        return tuple(0.0 for _ in peaks)
    return tuple(round(peak / ceiling, 4) for peak in peaks)


async def measure(clip: Clip, *, floor_db: float, buckets: int) -> Acoustics:
    """Measure ``clip``: speech spans, envelope, mean level."""
    return await anyio.to_thread.run_sync(_measure, clip, floor_db, buckets)


# -- everything below runs in a worker thread, never on the event loop --


def _measure(clip: Clip, floor_db: float, buckets: int) -> Acoustics:
    librosa = _librosa()
    rate = clip.rate or 1

    try:
        # ``split`` returns sample-index pairs for the stretches that stay within
        # ``top_db`` of the clip's own peak, so the threshold is relative: a quiet
        # recording is not read as silent throughout, and a loud one does not report
        # its own noise floor as speech. That relativity is also the limitation —
        # music or traffic under the whole clip is "non-silent" here, and the
        # transcript's confidence is what has to catch that.
        intervals = librosa.effects.split(clip.samples, top_db=floor_db)
        frames = librosa.feature.rms(y=clip.samples)[0]
        level = float(librosa.amplitude_to_db(_mean(frames), ref=1.0)[0])
    except Exception as exc:
        raise PipelineError(
            "The audio signal could not be measured.",
            details={"reason": type(exc).__name__},
        ) from exc

    return Acoustics(
        duration=clip.seconds,
        rate=clip.rate,
        spans=tuple(
            Span(start=int(start) / rate, end=int(end) / rate)
            for start, end in intervals
        ),
        envelope=envelope([float(value) for value in frames], buckets),
        level_db=level,
        truncated=clip.truncated,
    )


def _mean(frames: Any) -> Any:
    numpy = _numpy()
    return numpy.asarray([float(frames.mean()) if len(frames) else 0.0])


def _librosa() -> Any:
    try:
        import librosa
    except ImportError as exc:
        raise ConfigurationError(
            "librosa is required to measure submitted audio.",
            details={"missing": "librosa", "install": "pip install librosa"},
        ) from exc
    return librosa


def _numpy() -> Any:
    try:
        import numpy
    except ImportError as exc:
        raise ConfigurationError(
            "numpy is required to measure submitted audio.",
            details={"missing": "numpy", "install": "pip install numpy"},
        ) from exc
    return numpy
