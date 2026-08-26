"""Audio decoding, measurement and transcription.

Three modules with one seam. :mod:`app.audio.decode` produces a waveform,
:mod:`app.audio.analyse` measures it, and whatever ``TRANSCRIBER`` names turns it
into words. Only the last is a registry, because it is the only one with a plausible
second implementation — faster-whisper runs the same weights on a different runtime,
and a hosted endpoint runs them on someone else's machine.

Importing this package costs nothing: ``librosa``, ``numpy`` and ``whisper`` are all
imported inside function bodies, so it loads on a machine with none of them and a
missing one becomes a :class:`app.core.errors.ConfigurationError` naming its install
command.
"""

from __future__ import annotations

from app.audio.base import (
    Acoustics,
    Clip,
    Span,
    Transcriber,
    Transcript,
    Utterance,
)
from app.audio.transcribe import WhisperTranscriber
from app.core.config import Settings, SpeechProvider
from app.core.registry import ProviderRegistry

transcribers: ProviderRegistry[SpeechProvider, Transcriber] = ProviderRegistry(
    "transcriber"
)

transcribers.register(SpeechProvider.WHISPER, WhisperTranscriber)


def get_transcriber(settings: Settings) -> Transcriber:
    return transcribers.resolve(settings.TRANSCRIBER, settings)


__all__ = [
    "Acoustics",
    "Clip",
    "Span",
    "Transcriber",
    "Transcript",
    "Utterance",
    "WhisperTranscriber",
    "get_transcriber",
    "transcribers",
]
