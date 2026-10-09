"""The audio desk: what it hears, what it refuses to believe, and what it files.

Driven entirely through the seams, with a fake transcriber in place of Whisper and
the decode and measure steps substituted, so none of this needs ffmpeg, librosa,
numpy or torch installed. Same split as :mod:`tests.test_desk_image`: the libraries
recognise things and are tested where they are called; this file tests the decisions
taken around them.

The decisions worth breaking a build over, each with a test below:

* the recovered speech goes through the *text* pipeline, unchanged, as a text
  artifact — a recording is a delivery mechanism for a claim, not a second kind of
  claim needing a second verification path;
* a silent recording is an insufficiency, and the transcriber is never even
  resolved — a decoder handed room tone emits its most likely continuation, and
  that sentence must not become a checked claim;
* an utterance the waveform does not support is discarded, and does not appear in
  the published transcript either;
* the acoustic measurements are measurements. None of them moves a determination.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

import pytest

from app.audio import transcribers
from app.audio.base import Acoustics, Clip, Span, Transcript, Utterance
from app.core.config import Settings, SpeechProvider
from app.core.errors import ValidationError
from app.desks import audio as module
from app.desks.audio import AudioDesk
from app.domain import Artifact, ArtifactKind, Desk, Determination
from app.graph.verdict import ClaimRuling, Judgement, Ruling
from app.media import fetch as network
from app.reasoning.answer import Reasoning

RECORDING = Artifact(kind=ArtifactKind.AUDIO, url="https://example.test/clip.mp3")

#: A video artifact routes here too, and is handled by demuxing to the audio track.
FOOTAGE = Artifact(kind=ArtifactKind.VIDEO, url="https://example.test/clip.mp4")

#: What the fake fetch returns. Never decoded — the decoder here is a stub.
ENCODED = b"ID3\x04\x00 not really"


def configured(**overrides: Any) -> Settings:
    """Test settings. ``_env_file=None`` keeps a developer's ``.env`` out of it."""
    return Settings(_env_file=None, **overrides)


# ------------------------------------------------------------------- doubles ----


class FakeTranscriber:
    """Returns a prepared transcript and records the clips it was handed.

    ``builds`` counts how many times the registry built one, which is what
    distinguishes "transcribe was not called" from "the model was never loaded" —
    and the second is the property the silence gate exists to provide.
    """

    name = "fake"

    def __init__(self, transcript: Transcript) -> None:
        self._transcript = transcript
        self.seen: list[Clip] = []
        self.builds = 0

    async def transcribe(self, clip: Clip) -> Transcript:
        self.seen.append(clip)
        return self._transcript


class FakeGraph:
    """The compiled workflow, reduced to what the desk reads off an outcome.

    Not the real :class:`app.graph.workflow.VerificationGraph`, which would pull in
    langgraph. Injected through the desk's ``graph`` argument, which exists for
    exactly this.
    """

    def __init__(self, ruling: Ruling, reasoning: tuple[Reasoning, ...] = ()) -> None:
        self._ruling = ruling
        self._reasoning = reasoning
        self.seen: list[Artifact] = []

    async def run(self, artifact: Artifact) -> Any:
        self.seen.append(artifact)
        return _Outcome(self._ruling, self._reasoning)


class _Outcome:
    """The graph's return value, reduced to the two fields a desk reads.

    ``reasoning`` empty is the keyless deployment: no model ran, so the report is
    the arithmetic's alone. Tests that care about the model's prose pass their own.
    """

    def __init__(self, ruling: Ruling, reasoning: tuple[Reasoning, ...] = ()) -> None:
        self.ruling = ruling
        self.reasoning = reasoning


#: What the substituted fetch was asked for: ``(url, accept)`` per call.
FETCHED: list[tuple[str | None, tuple[str, ...]]] = []

#: What the substituted decoder was handed.
DECODED: list[bytes] = []


@contextmanager
def bench(
    transcriber: FakeTranscriber,
    *,
    acoustics: Acoustics | None = None,
    clip: Clip | None = None,
    data: bytes = ENCODED,
) -> Iterator[None]:
    """Substitute the transcriber seam, the fetch, and both signal steps.

    ``decode`` and ``measure`` are replaced as module attributes on
    :mod:`app.desks.audio` rather than through their own registries, because they
    are not seams — there is one decoder and one measurement, and inventing a
    registry for each so a test could reach them would be a design decided by its
    test suite. Substituted here is also what keeps ffmpeg, librosa and numpy out of
    the run entirely.

    The registry is a module-level singleton with the real Whisper transcriber
    registered at import, so this restores what it displaced rather than clearing
    the key. Leaving the seam empty would turn every later resolve in the session
    into a 501 — the same trap :func:`tests.stubs.desk_bench` documents.
    """
    was = transcribers.factory(SpeechProvider.WHISPER)
    original_fetch = network.fetch
    original_decode = module.decode
    original_measure = module.measure
    decoded = clip if clip is not None else CLIP
    measured = acoustics if acoustics is not None else HEARD

    def built(_settings: Settings) -> FakeTranscriber:
        transcriber.builds += 1
        return transcriber

    async def served(
        url: str,
        *,
        timeout: float,
        limit: int,
        accept: tuple[str, ...] = (),
        allow_private: bool = False,
    ) -> bytes:
        FETCHED.append((url, accept))
        return data

    async def decode(data: bytes, *, max_seconds: float, timeout: float) -> Clip:
        DECODED.append(data)
        return decoded

    async def measure(clip: Clip, *, floor_db: float, buckets: int) -> Acoustics:
        return measured

    FETCHED.clear()
    DECODED.clear()
    transcribers.register(SpeechProvider.WHISPER, built)
    network.fetch = served
    module.decode = decode
    module.measure = measure
    try:
        yield
    finally:
        network.fetch = original_fetch
        module.decode = original_decode
        module.measure = original_measure
        if was is not None:
            transcribers.register(SpeechProvider.WHISPER, was)


def desk(
    transcript: Transcript,
    ruling: Ruling | None = None,
    *,
    settings: Settings | None = None,
) -> tuple[AudioDesk, FakeTranscriber, FakeGraph]:
    graph = FakeGraph(ruling if ruling is not None else RULING)
    built = AudioDesk(
        settings=settings if settings is not None else configured(),
        graph=cast("Any", graph),
    )
    return built, FakeTranscriber(transcript), graph


# ------------------------------------------------------------------ fixtures ----


def said(text: str, start: float, end: float, *, conf: float = 0.9) -> Utterance:
    return Utterance(text=text, start=start, end=end, confidence=conf)


#: A 24-second waveform. Short and slow on purpose: the rate here only has to make
#: ``Clip.seconds`` come out right, and a real 16 kHz array of this length would be
#: 384,000 floats for a test that never looks at a sample.
CLIP = Clip(samples=[0.0] * 2400, rate=100)

#: Five seconds of sound near the start, and nothing after it. The measurement the
#: desk trusts over the transcript.
HEARD = Acoustics(
    duration=24.0,
    rate=16_000,
    spans=(Span(0.2, 5.4),),
    envelope=(0.08, 0.94, 0.41, 0.02),
    level_db=-21.5,
)

SILENT = Acoustics(
    duration=24.0,
    rate=16_000,
    spans=(),
    envelope=(0.0, 0.0, 0.0, 0.0),
    level_db=-71.2,
)

#: Two real utterances inside the sounding span, and one fluent sentence over the
#: silence after it — the shape a decoder actually produces on a recording that ends
#: in room tone. The third is what the gate exists to remove.
SPEECH = Transcript(
    utterances=(
        said("The central bank held the rate", 0.4, 3.1),
        said("at 5.25%.", 3.2, 5.0),
        said("Subtitles by the Amara community.", 20.4, 23.6),
    ),
    language="en",
    model="whisper base",
)

#: The same two, plus a segment inside the span that the decoder itself was unsure
#: of. Dropped by confidence rather than by the waveform.
MUMBLED = Transcript(
    utterances=(
        said("The central bank held the rate", 0.4, 3.1),
        said("at 5.25%.", 3.2, 5.0),
        said("and nine percent besides", 4.2, 5.3, conf=0.11),
    ),
    language="en",
    model="whisper base",
)

#: Everything the decoder returned sits over silence. Nothing survives the gate.
INVENTED = Transcript(
    utterances=(said("Thank you for watching this video.", 19.0, 23.0),),
    language="en",
    model="whisper base",
)

#: Real speech, inside the sounding span, and far too little of it to check.
BRIEF = Transcript(
    utterances=(said("Rate held.", 1.0, 2.4),),
    language="en",
    model="whisper base",
)

#: What :func:`app.audio.analyse.compose` makes of the surviving utterances.
TRANSCRIPT = "The central bank held the rate at 5.25%."

RULING = Ruling(
    judgement=Judgement.SUPPORTED,
    confidence=0.82,
    headline="The rate was held",
    rationale="Two independent outlets report the same decision.",
    claims=(
        ClaimRuling(
            ref=1,
            claim="The central bank held the rate at 5.25%.",
            judgement=Judgement.SUPPORTED,
            confidence=0.82,
        ),
    ),
)


# -------------------------------------------------------------- the pipeline ----


async def test_the_recovered_speech_is_submitted_as_a_text_artifact() -> None:
    """The whole design, in one assertion.

    A recording is a delivery mechanism for a claim, not a different kind of claim,
    so what reaches the graph is the transcript as prose — not the waveform, and not
    a reduced summary of it. Anything else would mean a second verification path
    that has to be kept in agreement with the first.
    """
    built, transcriber, graph = desk(SPEECH)

    with bench(transcriber):
        await built.examine(RECORDING)

    assert [a.kind for a in graph.seen] == [ArtifactKind.TEXT]
    assert graph.seen[0].content == TRANSCRIPT


async def test_the_decoder_is_handed_the_fetched_bytes() -> None:
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber, data=b"the fetched recording"):
        await built.examine(RECORDING)

    assert DECODED == [b"the fetched recording"]


async def test_the_transcriber_is_handed_the_decoded_clip() -> None:
    """One decode, and the same waveform is measured and transcribed.

    Which is why :class:`app.audio.base.Transcriber` takes a clip and not bytes: a
    transcriber decoding for itself would have the file demuxed twice, and the spans
    the gate trusts would describe something other than what was transcribed.
    """
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber):
        await built.examine(RECORDING)

    assert transcriber.seen == [CLIP]


async def test_the_desks_verdict_is_the_graphs_ruling() -> None:
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber):
        report = await built.examine(RECORDING)

    assert report.desk is Desk.AUDIO
    assert report.verdict.determination is Determination.SUPPORTED
    assert report.verdict.headline == "The rate was held"
    assert report.verdict.confidence == pytest.approx(0.82)


async def test_a_refuted_ruling_reaches_the_wire_as_contradicted() -> None:
    """``Judgement`` and ``Determination`` are different vocabularies."""
    refuted = Ruling(
        judgement=Judgement.REFUTED,
        confidence=0.91,
        headline="No such decision was taken",
        rationale="The published minutes record a cut.",
    )
    built, transcriber, _ = desk(SPEECH, refuted)

    with bench(transcriber):
        report = await built.examine(RECORDING)

    assert report.verdict.determination is Determination.CONTRADICTED


async def test_an_audio_artifact_without_a_url_is_a_validation_error() -> None:
    """Nothing to fetch, and not a finding about anything."""
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber), pytest.raises(ValidationError, match="needs a URL"):
        await built.examine(Artifact(kind=ArtifactKind.AUDIO, content="pasted"))


# --------------------------------------------------------------------- video ----


def test_the_desk_opens_on_footage_as_well_as_recordings() -> None:
    """``DEFAULT_DESKS`` routes a video artifact here, so it must accept one.

    What this desk rules on is what was *said* in the footage. Nothing here looks at
    the picture; that is ``Desk.VIDEO``, which is not built.
    """
    assert AudioDesk.kinds == frozenset({ArtifactKind.AUDIO, ArtifactKind.VIDEO})


async def test_footage_is_examined_through_its_audio_track() -> None:
    built, transcriber, graph = desk(SPEECH)

    with bench(transcriber):
        report = await built.examine(FOOTAGE)

    assert graph.seen[0].content == TRANSCRIPT
    assert report.desk is Desk.AUDIO


async def test_both_media_families_are_accepted_from_the_host() -> None:
    """A container's media type does not say whether it holds a picture.

    The same ``.mp4`` is served as ``video/mp4`` by one host and ``audio/mp4`` by
    another, so narrowing the accepted prefixes by artifact kind would reject
    working files.
    """
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber):
        await built.examine(RECORDING)

    assert [(RECORDING.url, ("audio/", "video/"))] == FETCHED


# ------------------------------------------------------------ nothing to hear ----


async def test_a_silent_recording_is_insufficient_not_false() -> None:
    """Silence says nothing, which is not a claim to rule on.

    Reporting anything else would publish a determination about a claim that was
    never extracted, let alone checked.
    """
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber, acoustics=SILENT):
        report = await built.examine(RECORDING)

    assert report.verdict.determination is Determination.INSUFFICIENT
    assert report.verdict.confidence == 0.0
    assert report.annotations == ()
    assert "No speech detected" in report.verdict.headline


async def test_a_silent_recording_never_loads_a_model() -> None:
    """The gate is before the transcriber is resolved, not inside it.

    What is being avoided is the model load and its first-use weights download —
    hundreds of megabytes to conclude what the silence floor already reported.
    """
    built, transcriber, graph = desk(SPEECH)

    with bench(transcriber, acoustics=SILENT):
        await built.examine(RECORDING)

    assert transcriber.builds == 0
    assert transcriber.seen == []
    assert graph.seen == []


async def test_the_silence_finding_still_reports_the_measurements() -> None:
    """Otherwise a silent upload and a working model handed music look identical."""
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber, acoustics=SILENT):
        report = await built.examine(RECORDING)

    ledger = {entry.key: entry.value for entry in report.ledger}
    assert ledger["Duration"] == "0:24"
    assert ledger["Speech"] == "0:00"
    assert ledger["Mean level"] == "-71.2 dBFS"
    assert "carried sound above the silence floor" in report.verdict.rationale


async def test_speech_entirely_over_silence_is_insufficient() -> None:
    """The anti-hallucination path, end to end.

    Every utterance the decoder returned sits outside the sounding spans, so nothing
    survives the gate, so no claim is submitted. A sign-off nobody said must not
    arrive as a checked claim with a determination against it.
    """
    built, transcriber, graph = desk(INVENTED)

    with bench(transcriber):
        report = await built.examine(RECORDING)

    assert graph.seen == []
    assert report.verdict.determination is Determination.INSUFFICIENT
    assert "No verifiable speech recovered" in report.verdict.headline
    assert report.detail is not None
    assert report.detail.text == ""
    assert report.detail.cues == ()


async def test_too_little_speech_to_stand_behind_is_insufficient() -> None:
    """Two words is not a claim, and researching them costs a search-provider call
    to conclude what the character count already said."""
    built, transcriber, graph = desk(BRIEF)

    with bench(transcriber):
        report = await built.examine(RECORDING)

    assert graph.seen == []
    assert report.verdict.determination is Determination.INSUFFICIENT


async def test_the_text_threshold_is_configurable() -> None:
    built, transcriber, graph = desk(BRIEF, settings=configured(AUDIO_MIN_TEXT_CHARS=5))

    with bench(transcriber):
        report = await built.examine(RECORDING)

    assert graph.seen != []
    assert report.verdict.determination is Determination.SUPPORTED


# ---------------------------------------------------------------- the gate ----


async def test_an_utterance_the_waveform_does_not_support_is_discarded() -> None:
    """Two independent measures have to agree before words are believed.

    The third utterance is grammatical, fluent, and sits over five seconds of
    nothing. The waveform is what settles it.
    """
    built, transcriber, graph = desk(SPEECH)

    with bench(transcriber):
        await built.examine(RECORDING)

    assert "Amara" not in (graph.seen[0].content or "")


async def test_an_utterance_the_decoder_doubted_is_discarded() -> None:
    """The second half of the gate: sound under it is not enough on its own."""
    built, transcriber, graph = desk(MUMBLED)

    with bench(transcriber):
        await built.examine(RECORDING)

    assert graph.seen[0].content == TRANSCRIPT


async def test_the_confidence_floor_is_configurable() -> None:
    built, transcriber, graph = desk(
        MUMBLED, settings=configured(AUDIO_MIN_CONFIDENCE=0.05)
    )

    with bench(transcriber):
        await built.examine(RECORDING)

    assert "nine percent" in (graph.seen[0].content or "")


async def test_a_discarded_segment_is_reported_but_moves_nothing() -> None:
    """The count is published; the determination is the one the evidence produced.

    A discarded segment is a fact about the transcription, not a finding about the
    claim, and a signal is where facts about the transcription go.
    """
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber):
        report = await built.examine(RECORDING)

    assert report.verdict.determination is Determination.SUPPORTED
    discarded = next(s for s in report.signals if s.label == "Segments discarded")
    assert discarded.reading == "1 unsupported by the waveform"


async def test_nothing_is_reported_discarded_when_nothing_was() -> None:
    """Rather than a row reading zero, which says nothing."""
    kept = Transcript(
        utterances=SPEECH.utterances[:2], language="en", model="whisper base"
    )
    built, transcriber, _ = desk(kept)

    with bench(transcriber):
        report = await built.examine(RECORDING)

    assert [s.label for s in report.signals] == ["Speech recovered", "Speech density"]


# -------------------------------------------------------- what a reader sees ----


async def test_every_annotation_quotes_the_transcript_verbatim() -> None:
    """The frontend does ``copy.indexOf(annotation.quote)`` and drops a miss.

    A quote taken from the ruling's normalised claim string rather than from the
    words the model produced appears nowhere in the transcript, and the marker
    silently never renders.
    """
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber):
        report = await built.examine(RECORDING)

    assert report.annotations
    assert report.detail is not None
    for annotation in report.annotations:
        assert annotation.quote in report.detail.text


async def test_an_annotation_points_at_the_claim_it_came_from() -> None:
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber):
        report = await built.examine(RECORDING)

    annotation = report.annotations[0]
    assert annotation.ref == 1
    assert annotation.determination is Determination.SUPPORTED
    assert annotation.quote == TRANSCRIPT


async def test_only_the_utterances_that_survived_are_published() -> None:
    """Publishing the discarded ones would put text on the page that this desk has
    just decided was not said.

    The count in the ledger is the honest way to report them: a reader is told one
    segment was dropped, and is not shown a sentence alongside a verdict that had
    nothing to do with it.
    """
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber):
        report = await built.examine(RECORDING)

    assert report.detail is not None
    assert [cue.text for cue in report.detail.cues] == [
        "The central bank held the rate",
        "at 5.25%.",
    ]


async def test_a_cue_carries_the_ruling_its_words_were_read_into() -> None:
    """Which is what lets the reader highlight the segment a verdict came from."""
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber):
        report = await built.examine(RECORDING)

    assert report.detail is not None
    assert [cue.ref for cue in report.detail.cues] == [1, 1]
    assert report.detail.cues[0].start == pytest.approx(0.4)
    assert report.detail.cues[0].end == pytest.approx(3.1)


async def test_the_detail_carries_the_transcript_that_was_checked() -> None:
    """So a record can be re-read without the recording, which may be gone."""
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber):
        report = await built.examine(RECORDING)

    assert report.detail is not None
    assert report.detail.text == TRANSCRIPT
    assert report.detail.language == "en"
    assert report.detail.duration == pytest.approx(24.0)


async def test_spans_are_fractions_of_the_runtime() -> None:
    """Seconds would line up under exactly one waveform width."""
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber):
        report = await built.examine(RECORDING)

    assert report.detail is not None
    start, end = report.detail.spans[0]
    assert start == pytest.approx(0.2 / 24.0, abs=1e-4)
    assert end == pytest.approx(5.4 / 24.0, abs=1e-4)
    assert all(0.0 <= edge <= 1.0 for span in report.detail.spans for edge in span)


async def test_the_envelope_is_published_for_drawing() -> None:
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber):
        report = await built.examine(RECORDING)

    assert report.detail is not None
    assert report.detail.envelope == HEARD.envelope


# ------------------------------------------------------------------- ledger ----


async def test_the_ledger_records_how_the_recording_was_heard() -> None:
    """Which is what makes a poor transcript diagnosable from a stored record.

    Without the level and the segment counts, a thin result is only explicable by
    re-running with the original file in hand.
    """
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber):
        report = await built.examine(RECORDING)

    ledger = {entry.key: entry.value for entry in report.ledger}
    assert ledger["Duration"] == "0:24"
    assert ledger["Speech"] == "0:05"
    assert ledger["Mean level"] == "-21.5 dBFS"
    assert ledger["Segments heard"] == "2 of 3"
    assert ledger["Words heard"] == "8"
    assert ledger["Transcriber"] == "whisper base"
    assert ledger["Language"] == "en"
    assert ledger["Claims ruled"] == "1"


async def test_a_truncated_clip_says_so_on_the_record() -> None:
    """A record that omits the cut implies the whole recording was heard.

    Which matters most in the case this desk cannot otherwise distinguish: a clip
    exactly as long as the ceiling looks identical to one that ran to its end.
    """
    built, transcriber, _ = desk(SPEECH)
    cut = Acoustics(
        duration=HEARD.duration,
        rate=HEARD.rate,
        spans=HEARD.spans,
        envelope=HEARD.envelope,
        level_db=HEARD.level_db,
        truncated=True,
    )

    with bench(transcriber, acoustics=cut):
        report = await built.examine(RECORDING)

    assert ("Truncated at", "0:24") in {(e.key, e.value) for e in report.ledger}


async def test_a_complete_clip_reports_no_truncation() -> None:
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber):
        report = await built.examine(RECORDING)

    assert "Truncated at" not in {entry.key for entry in report.ledger}


async def test_speech_density_is_measured_against_the_whole_runtime() -> None:
    """A recording that is 20% speech is not thereby 20% true.

    It is reported as a reading with a weight, next to the other measurements, and
    the determination above it is untouched.
    """
    built, transcriber, _ = desk(SPEECH)

    with bench(transcriber):
        report = await built.examine(RECORDING)

    density = next(s for s in report.signals if s.label == "Speech density")
    assert density.reading == "22% of runtime"
    assert density.weight == pytest.approx(5.2 / 24.0, abs=1e-4)
    assert report.verdict.determination is Determination.SUPPORTED
