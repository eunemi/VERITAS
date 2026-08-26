"""Whisper transcription.

``whisper`` and the checkpoint behind it are both deferred: the import pulls in
torch, and the first call for a given model downloads weights. A deployment that
never receives audio pays for neither. The model is cached per process behind a
lock, exactly as the detector's weights are.

Every decoding option that could make two runs of one file disagree is pinned here
rather than left to the library's defaults. A transcript is quoted verbatim in a
published annotation, so it has to be reproducible.
"""

from __future__ import annotations

import math
import threading
from typing import Any

import anyio.to_thread

from app.audio.base import Clip, Transcript, Utterance
from app.audio.decode import SAMPLE_RATE
from app.core.config import Settings
from app.core.errors import ConfigurationError, PipelineError

_LOAD_LOCK = threading.Lock()
#: Whisper's decoder holds per-call state on the model, and its ``transcribe``
#: helper is not written to be reentrant. Two requests sharing one loaded model
#: without this produce two interleaved transcripts.
_RUN_LOCK = threading.Lock()
_MODELS: dict[tuple[str, str, str], Any] = {}


def load(model: str, *, device: str, root: str | None = None) -> Any:
    """The named model, loaded at most once per process."""
    key = (model, device, root or "")
    cached = _MODELS.get(key)
    if cached is not None:
        return cached

    with _LOAD_LOCK:
        present = _MODELS.get(key)
        if present is not None:
            return present
        built = _build(model, device, root)
        _MODELS[key] = built
        return built


def _build(model: str, device: str, root: str | None) -> Any:
    whisper = _whisper()
    try:
        return whisper.load_model(model, device=device, download_root=root)
    except Exception as exc:
        # Broad on purpose. The name is resolved by downloading it, so the failures
        # span whisper's HTTP fetch, its checksum check, torch's deserialiser and
        # the filesystem — and none of those exception types are public API.
        raise ConfigurationError(
            "The transcription model could not be loaded.",
            details={
                "model": model,
                "device": device,
                "reason": str(exc).strip()[:200],
                "hint": "Weights are downloaded on first use; set "
                "WHISPER_DOWNLOAD_ROOT to a warm cache for a sealed deployment.",
            },
        ) from exc


class WhisperTranscriber:
    """Transcribes a clip with openai-whisper."""

    name = "whisper"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def transcribe(self, clip: Clip) -> Transcript:
        if clip.rate != SAMPLE_RATE:
            raise PipelineError(
                "Transcription requires audio at the model's own sample rate.",
                details={"rate": clip.rate, "expected": SAMPLE_RATE},
            )
        return await anyio.to_thread.run_sync(self._transcribe, clip)

    # -- everything below runs in a worker thread, never on the event loop --

    def _transcribe(self, clip: Clip) -> Transcript:
        settings = self._settings
        model = load(
            settings.WHISPER_MODEL,
            device=settings.WHISPER_DEVICE,
            root=settings.WHISPER_DOWNLOAD_ROOT,
        )

        try:
            with _RUN_LOCK:
                payload = model.transcribe(
                    clip.samples,
                    language=settings.WHISPER_LANGUAGE,
                    # Transcribe, never translate. Translation paraphrases, and a
                    # paraphrased sentence checked as a claim is a claim nobody
                    # made — it also stops the quote matching the transcript.
                    task="transcribe",
                    # Greedy, so one file gives one transcript. Whisper's default
                    # is a temperature ladder it climbs whenever a segment looks
                    # poor, which samples and therefore makes runs disagree.
                    temperature=0.0,
                    # The decoder normally conditions each window on the text it
                    # just produced. That is what makes it repeat a phrase for
                    # minutes once it starts, and each repetition would arrive here
                    # as another utterance to extract claims from.
                    condition_on_previous_text=False,
                    fp16=settings.WHISPER_DEVICE != "cpu",
                )
        except Exception as exc:
            raise PipelineError(
                "Transcription failed.",
                details={"reason": str(exc).strip()[:200]},
            ) from exc

        return Transcript(
            utterances=_read(payload, settings.WHISPER_NO_SPEECH_CEILING),
            language=str(payload.get("language") or ""),
            model=settings.WHISPER_MODEL,
        )


def _read(payload: Any, ceiling: float) -> tuple[Utterance, ...]:
    found: list[Utterance] = []
    for segment in payload.get("segments") or ():
        text = str(segment.get("text") or "").strip()
        if not text:
            continue

        # The model's own estimate that this window holds no speech. It is a second
        # opinion on the same question :func:`app.audio.analyse.voiced` asks of the
        # waveform, and it is cheap to honour here: a segment the decoder itself
        # thinks is silence is exactly the one whose text it invented.
        if float(segment.get("no_speech_prob") or 0.0) > ceiling:
            continue

        start = float(segment.get("start") or 0.0)
        found.append(
            Utterance(
                text=text,
                start=start,
                end=max(start, float(segment.get("end") or 0.0)),
                confidence=_confidence(segment.get("avg_logprob")),
            )
        )
    return tuple(found)


def _confidence(logprob: Any) -> float:
    """Mean token log-probability as a 0–1 number.

    Exponentiating a mean log-probability gives the geometric mean likelihood of the
    tokens chosen — how sure the decoder was of its own words, which is not the same
    as how likely those words are to be right. Confidently wrong is a normal failure
    mode for a speech model, so this gates and is reported, and never scores.
    """
    if logprob is None:
        return 0.0
    try:
        return min(1.0, max(0.0, math.exp(float(logprob))))
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _whisper() -> Any:
    try:
        import whisper
    except ImportError as exc:
        raise ConfigurationError(
            "openai-whisper is required to transcribe audio.",
            details={
                "missing": "whisper",
                "install": "pip install openai-whisper",
            },
        ) from exc
    return whisper
