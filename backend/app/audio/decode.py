"""Getting a waveform out of whatever was submitted.

Two paths, and which one runs is decided by whether the first works.

libsndfile — reached through ``librosa.load``, which accepts a file object — reads
wav, flac, ogg and (since 1.1) mp3 with no external binary at all. It does not
demux: an mp4, mov, webm or mkv is a container with a video stream in it, and
libsndfile has no idea what to do with one. Every video submission and a few audio
ones therefore fall through to ffmpeg, which is a separate artifact a deploy has to
install, exactly as the Tesseract binary is.

Both paths produce the same thing: mono float32 at :data:`SAMPLE_RATE`.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from io import BytesIO
from typing import Any

import anyio.to_thread

from app.audio.base import Clip
from app.core.errors import (
    ConfigurationError,
    PipelineError,
    UnsupportedMediaTypeError,
)

logger = logging.getLogger(__name__)

#: Whisper's input rate, and not a setting. Its encoder was trained on 16 kHz mono
#: log-mel frames and the hop length is fixed against that, so handing it 44.1 kHz
#: does not transcribe faster or better — it transcribes something at the wrong
#: speed. Resampling here rather than inside the transcriber is what lets the signal
#: analysis measure the same waveform the model heard.
SAMPLE_RATE = 16_000

#: Fewest samples worth transcribing, at 25 ms the length of one phoneme.
MIN_SAMPLES = SAMPLE_RATE // 40


async def decode(data: bytes, *, max_seconds: float, timeout: float) -> Clip:
    """Decode ``data`` to mono float32 at :data:`SAMPLE_RATE`.

    Truncates at ``max_seconds`` rather than refusing an over-long file, and records
    on the clip that it did. ``timeout`` bounds ffmpeg only.
    """
    return await anyio.to_thread.run_sync(_decode, data, max_seconds, timeout)


# -- everything below runs in a worker thread, never on the event loop --


def _decode(data: bytes, max_seconds: float, timeout: float) -> Clip:
    decoded = _native(data, max_seconds)
    if decoded is None:
        decoded = _ffmpeg(data, max_seconds, timeout)
    samples, rate = decoded

    if len(samples) < MIN_SAMPLES:
        raise UnsupportedMediaTypeError(
            "The submitted file carries no audio to transcribe.",
            details={"samples": len(samples), "minimum": MIN_SAMPLES},
        )

    seconds = len(samples) / rate
    # Equality against the ceiling, with a frame of slack: a decoder asked to stop
    # at 1800 seconds lands a few milliseconds either side of it, and a file that is
    # genuinely 1800 seconds long is reported as truncated. Overstating the cut is
    # the safe direction — the alternative is a report implying the whole recording
    # was heard when the tail was dropped.
    return Clip(
        samples=samples,
        rate=rate,
        truncated=seconds >= max_seconds - 0.05,
    )


def _native(data: bytes, max_seconds: float) -> tuple[Any, int] | None:
    """Decode with libsndfile, or return ``None`` for a container it cannot read.

    Every failure is a fall-through rather than an error. The exceptions worth
    distinguishing here belong to librosa's backends — ``soundfile.LibsndfileError``,
    ``audioread.NoBackendError`` — and importing either to name it would make a
    backend detail a hard dependency of this module in order to decide something
    ffmpeg is about to decide anyway.
    """
    librosa = _librosa()
    try:
        samples, rate = librosa.load(
            BytesIO(data), sr=SAMPLE_RATE, mono=True, duration=max_seconds
        )
    except Exception as exc:
        logger.debug("libsndfile could not read the container: %s", exc)
        return None
    return samples, int(rate)


def _ffmpeg(data: bytes, max_seconds: float, timeout: float) -> tuple[Any, int]:
    """Demux and decode with ffmpeg, over pipes.

    stdin and stdout rather than temporary files, so nothing submitted is ever
    written to this filesystem and there is no path for the process to clean up.
    """
    numpy = _numpy()
    binary = shutil.which("ffmpeg")
    if binary is None:
        raise ConfigurationError(
            "ffmpeg is required to read audio out of this container.",
            details={
                "missing": "ffmpeg",
                "install": "brew install ffmpeg (or: apt-get install ffmpeg)",
            },
        )

    try:
        # Fixed argument vector, no shell, and the only caller-supplied value is the
        # file arriving on stdin — ffmpeg is never handed the submitted URL, a path,
        # or anything else a caller wrote.
        done = subprocess.run(  # noqa: S603
            [binary, *_arguments(max_seconds)],
            input=data,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise PipelineError(
            "Decoding the submitted file timed out.",
            details={"seconds": timeout},
        ) from exc

    if done.returncode != 0 or not done.stdout:
        raise UnsupportedMediaTypeError(
            "The submitted file could not be decoded, or holds no audio stream.",
            details={"reason": done.stderr.decode("utf-8", "replace").strip()[:200]},
        )

    # ``frombuffer`` is a read-only view over bytes this function owns, and torch
    # refuses to wrap a non-writable array without warning about it. ``astype``
    # copies, and copying to the native ``float32`` also fixes the byte order on a
    # big-endian host, where ``<f4`` would otherwise arrive byte-swapped.
    samples = numpy.frombuffer(done.stdout, dtype="<f4").astype(
        numpy.float32, copy=True
    )
    return samples, SAMPLE_RATE


def _arguments(max_seconds: float) -> list[str]:
    return [
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        # Drop the picture and take the first audio stream only. Without ``-map`` a
        # file with a commentary track as well as the programme audio is mixed down
        # into one, which puts two people's words in the same sentence.
        "-vn",
        "-map",
        "0:a:0",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-t",
        f"{max_seconds:.3f}",
        # Raw 32-bit float, little-endian: no container, no header to parse, and the
        # exact memory layout numpy reads below.
        "-f",
        "f32le",
        "pipe:1",
    ]


def _librosa() -> Any:
    try:
        import librosa
    except ImportError as exc:
        raise ConfigurationError(
            "librosa is required to read submitted audio.",
            details={"missing": "librosa", "install": "pip install librosa"},
        ) from exc
    return librosa


def _numpy() -> Any:
    try:
        import numpy
    except ImportError as exc:
        raise ConfigurationError(
            "numpy is required to read submitted audio.",
            details={"missing": "numpy", "install": "pip install numpy"},
        ) from exc
    return numpy
