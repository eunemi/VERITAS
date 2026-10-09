"""The audio desk: hear the recording, then verify what was said.

Same shape as the image desk, and for the same reason. Whisper recovers the words,
and the existing graph — claim extraction, search, fact-check lookup, evidence
scoring, source credibility, contradiction detection, the judge — rules on them
exactly as it would on the same sentence pasted in as prose. A recording is a
delivery mechanism for a claim.

It handles video as well as audio, because a video artifact routes here (see
``DEFAULT_DESKS``) and its audio track is what carries the claims;
:mod:`app.audio.decode` demuxes to reach it. It does not examine the picture —
frames, cuts, continuity, whether the footage is generated — and nothing it files
should be read as a finding about the images. :data:`app.domain.Desk.VIDEO` is where
that will live when it is built.

The gate in :meth:`AudioDesk._heard` is the part that matters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.audio import get_transcriber
from app.audio.analyse import compose, confident, measure, voiced
from app.audio.base import Acoustics, Transcript, Utterance
from app.audio.decode import decode
from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError, ValidationError
from app.desks.anchors import attach
from app.desks.graph import compiled, model_ledger, readings
from app.domain import (
    Artifact,
    ArtifactKind,
    AudioDetail,
    Desk,
    DeskReport,
    Determination,
    LedgerEntry,
    Signal,
    TranscriptCue,
    Verdict,
)
from app.graph.verdict import Ruling, as_determination
from app.media import fetch

if TYPE_CHECKING:
    from app.graph.workflow import Outcome, VerificationGraph

_SILENT = (
    "No speech detected",
    "No stretch of this recording rose above the silence floor, so it was never "
    "transcribed",
)
_UNCLEAR = (
    "No verifiable speech recovered",
    "Transcription recovered too little speech this desk was willing to stand "
    "behind, so no claim was submitted for verification",
)


class AudioDesk:
    """Examines recordings: speech recovered by ASR, ruled on by the pipeline."""

    desk = Desk.AUDIO
    kinds = frozenset({ArtifactKind.AUDIO, ArtifactKind.VIDEO})

    def __init__(
        self, *, settings: Settings, graph: VerificationGraph | None = None
    ) -> None:
        self._settings = settings
        self._own = graph

    async def examine(
        self, artifact: Artifact, *, verification_id: str | None = None
    ) -> DeskReport:
        settings = self._settings
        try:
            clip = await decode(
                await self._fetch(artifact),
                max_seconds=settings.AUDIO_MAX_SECONDS,
                timeout=settings.AUDIO_DECODE_TIMEOUT_SECONDS,
            )
            acoustics = await measure(
                clip,
                floor_db=settings.AUDIO_SILENCE_FLOOR_DB,
                buckets=settings.AUDIO_ENVELOPE_BUCKETS,
            )

            # Checked before the transcriber is resolved, because loading a model and
            # its first-use weight download is the expensive part of this desk and a
            # clip with no sound in it has nothing for the model to find.
            if acoustics.speech_seconds < settings.AUDIO_MIN_SPEECH_SECONDS:
                return self._unheard(Transcript(()), acoustics, (), _SILENT)

            transcript = await get_transcriber(settings).transcribe(clip)
        except ConfigurationError as exc:
            import logging

            logging.getLogger(__name__).warning(
                "Audio desk missing dependencies: %s", exc
            )
            return self._audio_unavailable()

        heard = self._heard(transcript, acoustics)
        text = compose(heard)

        if len(text.strip()) < settings.AUDIO_MIN_TEXT_CHARS:
            return self._unheard(transcript, acoustics, heard, _UNCLEAR)

        outcome = await self._graph().run(
            Artifact(kind=ArtifactKind.TEXT, content=text)
        )
        return self._filed(transcript, acoustics, heard, text, outcome)

    # ------------------------------------------------------------ steps ----

    async def _fetch(self, artifact: Artifact) -> bytes:
        if not artifact.url:
            raise ValidationError(
                "An audio artifact needs a URL to fetch.",
                details={"desk": str(self.desk)},
            )
        return await fetch.fetch(
            artifact.url,
            timeout=self._settings.MEDIA_FETCH_TIMEOUT_SECONDS,
            limit=self._settings.MAX_UPLOAD_BYTES,
            # Both prefixes for both kinds. A container's media type does not say
            # whether it holds a picture: the same ``.mp4`` is served as
            # ``video/mp4`` by one host and ``audio/mp4`` by another, so narrowing
            # by kind here would reject working files.
            accept=("audio/", "video/"),
            allow_private=(
                self._settings.MEDIA_ALLOW_PRIVATE_HOSTS
                or fetch.is_managed_upload_url(
                    artifact.url, public_api_url=self._settings.PUBLIC_API_URL
                )
            ),
        )

    def _heard(
        self, transcript: Transcript, acoustics: Acoustics
    ) -> tuple[Utterance, ...]:
        """Keep only utterances two independent measures agree were spoken.

        A speech recogniser handed silence does not return nothing. Its decoder
        emits the most likely continuation, which over room tone is reliably a
        fluent sentence nobody said — a channel sign-off, a subtitling credit. Left
        alone that sentence is extracted as a claim, researched, and published with
        a determination against it: a verdict on words never spoken.

        So an utterance survives only if the waveform independently shows sound
        under it and the decoder was reasonably sure of its own tokens. Losing real
        speech is the acceptable failure here; the alternative is inventing it.
        """
        settings = self._settings
        return confident(
            voiced(
                transcript.utterances,
                acoustics.spans,
                floor=settings.AUDIO_MIN_VOICED_RATIO,
            ),
            floor=settings.AUDIO_MIN_CONFIDENCE,
        )

    def _graph(self) -> VerificationGraph:
        return self._own or compiled(self._settings)

    # ----------------------------------------------------------- filing ----

    def _audio_unavailable(self) -> DeskReport:
        """Returns a graceful error report when audio dependencies are not installed."""
        return DeskReport(
            desk=self.desk,
            verdict=Verdict(
                determination=Determination.INSUFFICIENT,
                headline="Audio Transcription Unavailable",
                rationale="System dependencies for audio processing (Whisper/Librosa/FFmpeg) are not installed. Cannot process audio.",
                confidence=0.0,
            ),
            ledger=(LedgerEntry("Audio", "Unavailable"),),
            signals=(),
            detail=AudioDetail(
                duration=0.0, language="", text="", envelope=(), spans=(), cues=()
            ),
        )

    def _unheard(
        self,
        transcript: Transcript,
        acoustics: Acoustics,
        heard: tuple[Utterance, ...],
        because: tuple[str, str],
    ) -> DeskReport:
        """No usable speech. A finding about the recording, not about a claim."""
        headline, reason = because
        return DeskReport(
            desk=self.desk,
            verdict=Verdict(
                determination=Determination.INSUFFICIENT,
                headline=headline,
                rationale=f"{reason}. Measured: {_measured(acoustics)}.",
                confidence=0.0,
            ),
            ledger=self._ledger(transcript, acoustics, heard, None),
            signals=self._signals(transcript, acoustics, heard),
            detail=self._detail(acoustics, heard, "", {}, transcript.language),
        )

    def _filed(
        self,
        transcript: Transcript,
        acoustics: Acoustics,
        heard: tuple[Utterance, ...],
        text: str,
        outcome: Outcome,
    ) -> DeskReport:
        ruling = outcome.ruling
        anchors, annotations = attach(
            [(u.text.strip(), 0) for u in heard],
            ruling.claims,
            readings=readings(ruling.claims, outcome.reasoning),
        )
        return DeskReport(
            desk=self.desk,
            verdict=Verdict(
                determination=as_determination(ruling.judgement),
                headline=ruling.headline,
                rationale=ruling.rationale,
                confidence=ruling.confidence,
            ),
            ledger=(
                *self._ledger(transcript, acoustics, heard, ruling),
                *model_ledger(outcome.reasoning),
            ),
            annotations=annotations,
            signals=self._signals(transcript, acoustics, heard),
            detail=self._detail(acoustics, heard, text, anchors, transcript.language),
        )

    def _ledger(
        self,
        transcript: Transcript,
        acoustics: Acoustics,
        heard: tuple[Utterance, ...],
        ruling: Ruling | None,
    ) -> tuple[LedgerEntry, ...]:
        total = len(transcript.utterances)
        entries = [
            LedgerEntry("Duration", _clock(acoustics.duration)),
            LedgerEntry("Speech", _clock(acoustics.speech_seconds)),
            LedgerEntry("Mean level", f"{acoustics.level_db:.1f} dBFS"),
            LedgerEntry("Segments heard", f"{len(heard)} of {total}"),
            LedgerEntry("Words heard", str(_words(heard))),
        ]
        if transcript.model:
            entries.append(LedgerEntry("Transcriber", transcript.model))
        if transcript.language:
            entries.append(LedgerEntry("Language", transcript.language))
        if acoustics.truncated:
            entries.append(LedgerEntry("Truncated at", _clock(acoustics.duration)))
        if ruling is not None:
            entries.append(LedgerEntry("Claims ruled", str(len(ruling.claims))))
        return tuple(entries)

    def _signals(
        self,
        transcript: Transcript,
        acoustics: Acoustics,
        heard: tuple[Utterance, ...],
    ) -> tuple[Signal, ...]:
        """Measurements, never a verdict.

        None of these move the determination. A quiet recording is not a false one,
        and a low transcription confidence says the words are uncertain — not that
        the claim inside them is wrong. They are here so that a poor transcript is
        diagnosable rather than merely disappointing.
        """
        dropped = len(transcript.utterances) - len(heard)
        signals = [
            Signal(
                label="Speech recovered",
                reading=f"{_words(heard)} words",
                weight=_mean([u.confidence for u in heard]),
            ),
            Signal(
                label="Speech density",
                reading=f"{round(acoustics.speech_ratio * 100)}% of runtime",
                weight=acoustics.speech_ratio,
            ),
        ]
        if dropped > 0:
            signals.append(
                Signal(
                    label="Segments discarded",
                    reading=f"{dropped} unsupported by the waveform",
                    weight=min(1.0, dropped / len(transcript.utterances)),
                )
            )
        return tuple(signals)

    def _detail(
        self,
        acoustics: Acoustics,
        heard: tuple[Utterance, ...],
        text: str,
        anchors: dict[int, int],
        language: str,
    ) -> AudioDetail:
        """The exhibit a reader checks the verdict against.

        Only the utterances that survived :meth:`_heard` are published. Showing the
        discarded ones would put text on the page that this desk has just decided
        was not said, and the count in the ledger is the honest way to report them.
        """
        span = acoustics.duration or 1.0
        return AudioDetail(
            duration=acoustics.duration,
            language=language,
            text=text,
            envelope=acoustics.envelope,
            spans=tuple(
                (_fraction(s.start, span), _fraction(s.end, span))
                for s in acoustics.spans
            ),
            cues=tuple(
                TranscriptCue(
                    ref=anchors.get(index, 0),
                    start=utterance.start,
                    end=utterance.end,
                    text=utterance.text.strip(),
                )
                for index, utterance in enumerate(heard)
            ),
        )


def _words(utterances: tuple[Utterance, ...]) -> int:
    return sum(len(u.text.split()) for u in utterances)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return min(1.0, max(0.0, sum(values) / len(values)))


def _fraction(seconds: float, span: float) -> float:
    return round(min(1.0, max(0.0, seconds / span)), 4)


def _measured(acoustics: Acoustics) -> str:
    return (
        f"{_clock(acoustics.speech_seconds)} of {_clock(acoustics.duration)} "
        "carried sound above the silence floor"
    )


def _clock(seconds: float) -> str:
    whole = int(max(0.0, seconds))
    return f"{whole // 60}:{whole % 60:02d}"


def build(settings: Settings | None = None) -> AudioDesk:
    """Factory for the registry, which resolves desks with no arguments."""
    return AudioDesk(settings=settings or get_settings())
