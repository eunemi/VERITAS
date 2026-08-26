"""What a transcriber returns, what the signal analysis measures, and the contract.

Plain Python: no librosa, no numpy, no whisper. The types the audio desk and the
API schemas read are defined here so that both — and the tests around them — can be
exercised on a machine with none of the audio stack installed.

Times are seconds from the start of the *submitted* clip, as floats. Not samples,
because a caller would then need the rate to make sense of a number; and not
formatted timecodes, because a record that holds only ``"00:12"`` cannot be sorted,
compared or intersected with a span. Formatting happens on the wire, in
:mod:`app.schemas.verification`, exactly as it does for a confidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class Clip:
    """Decoded audio, ready for a model.

    ``samples`` is a one-dimensional array of amplitudes in −1..1 at ``rate`` hertz,
    mono. It is typed ``Any`` rather than ``numpy.ndarray`` because naming that type
    would put numpy into the one module in this package that must import nothing
    third party; :mod:`app.audio.decode` is the only thing that builds one.

    ``truncated`` records that the decoder stopped at a configured ceiling rather
    than at the end of the file. Carried rather than inferred, because a clip that
    is exactly as long as the limit is otherwise indistinguishable from one that was
    cut off — and a report that omits the difference implies the whole recording was
    heard.
    """

    samples: Any
    rate: int
    truncated: bool = False

    @property
    def seconds(self) -> float:
        if self.rate <= 0:
            return 0.0
        return len(self.samples) / self.rate


@dataclass(frozen=True, slots=True)
class Span:
    """A stretch of time, in seconds from the start of the clip."""

    start: float
    end: float

    @property
    def seconds(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True, slots=True)
class Utterance:
    """One segment of transcribed speech.

    ``confidence`` is 0–1 and is the model's own token likelihood for the segment,
    not a probability that the words are correct. It gates and it is reported; it
    never contributes to a verdict.
    """

    text: str
    start: float
    end: float
    confidence: float

    @property
    def seconds(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True, slots=True)
class Transcript:
    """Everything one transcription pass recovered.

    ``language`` is what the model was told or what it detected, kept because a
    transcript of English read as Welsh is fluent nonsense and the language is the
    only field that says so.
    """

    utterances: tuple[Utterance, ...]
    language: str = ""
    model: str = ""

    @property
    def words(self) -> int:
        return sum(len(u.text.split()) for u in self.utterances)


@dataclass(frozen=True, slots=True)
class Acoustics:
    """What the signal itself says, independent of any words recovered from it.

    Measured rather than inferred, and kept separate from :class:`Transcript` for
    one reason: these numbers are what make a poor transcript diagnosable. A record
    holding "no speech recovered" and nothing else cannot distinguish a silent
    upload from a working model that was handed music.

    ``spans`` are the stretches loud enough to be speech, and they are also the
    gate: see :func:`app.audio.analyse.voiced`.
    """

    duration: float
    rate: int
    spans: tuple[Span, ...] = ()
    #: The waveform reduced to one peak per bucket, each 0–1. For drawing.
    envelope: tuple[float, ...] = ()
    #: Mean level in decibels relative to full scale, so always negative.
    level_db: float = 0.0
    truncated: bool = False

    @property
    def speech_seconds(self) -> float:
        return sum(span.seconds for span in self.spans)

    @property
    def speech_ratio(self) -> float:
        if self.duration <= 0:
            return 0.0
        return min(1.0, self.speech_seconds / self.duration)


@runtime_checkable
class Transcriber(Protocol):
    """Turns decoded audio into words.

    Takes a :class:`Clip` rather than bytes, unlike
    :class:`app.vision.base.ImageReader`. Decoding is a separate step here because
    the signal analysis needs the same waveform the model does, and letting each
    transcriber decode for itself would mean demuxing the file twice and measuring
    something that might not be what was transcribed.

    Implementations raise from :mod:`app.core.errors` on failure — never a
    library-specific exception. A caller of this protocol has no way to import a
    torch error to catch it, and should not have to.
    """

    name: str

    async def transcribe(self, clip: Clip) -> Transcript: ...
