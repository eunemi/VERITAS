"""What a verification *is*.

Frozen dataclasses, not pydantic models. This mirrors the four provider seams,
whose value types (:class:`app.llm.Completion`, :class:`app.search.SearchResult`)
are frozen dataclasses for the same reason: these are the objects services and the
desk seam exchange with each other, and nothing about them should depend on a web
framework or on the shape the API happens to publish this month. The wire shapes
live in :mod:`app.schemas.verification` and convert from these.

State transitions are methods that return a *new* :class:`Verification`. A
verification is a record of an examination, and a record that can be edited in
place is one whose history you cannot trust; making each transition produce a new
value means the repository decides what to keep, and a caller cannot mutate a
record it merely read.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from app.domain.enums import (
    ADJUDICATOR,
    ArtifactKind,
    Desk,
    Determination,
    Relevance,
    Reliability,
    Status,
)
from app.utils.clock import utcnow
from app.utils.ids import new_id


@dataclass(frozen=True, slots=True)
class Artifact:
    """The thing submitted for examination.

    One type rather than a class per kind, because every consumer switches on
    ``kind`` anyway and the fields are near-identical. Which fields are required
    for which kind is enforced at the edge, in
    :mod:`app.schemas.verification` — by the time an ``Artifact`` exists it is
    already known to be coherent.

    ``url`` is a plain ``str`` holding exactly what the caller sent. The request
    schema validates it with ``HttpUrl`` and then discards the parsed object:
    pydantic's ``Url`` is not a ``str``, so letting it through would put pydantic
    underneath this layer, and it normalises — whether ``https://example.com``
    gains a trailing slash has changed within the supported pydantic range, which
    would make the URL echoed back by ``GET /verification/{id}`` depend on the
    installed patch version.
    """

    kind: ArtifactKind
    #: The submitted prose or claim, for ``TEXT`` and ``CLAIM``.
    content: str | None = None
    #: Where to fetch the artifact, for ``URL`` and the three media kinds.
    url: str | None = None
    #: Original file name, when the submitter had one. Display only.
    filename: str | None = None

    @property
    def is_media(self) -> bool:
        """True for image, audio and video — the kinds that need fetching."""
        return self.kind in {
            ArtifactKind.IMAGE,
            ArtifactKind.AUDIO,
            ArtifactKind.VIDEO,
        }


@dataclass(frozen=True, slots=True)
class Annotation:
    """A note anchored to an exact span of the artifact.

    ``ref`` is the exhibit number printed both in the margin and on the artifact,
    so it is a pointer and the numbering is meaningful: annotations are numbered
    from 1 in the order they appear in the artifact, not in the order the desk
    happened to find them.

    ``quote`` must be a verbatim substring of the artifact. The frontend locates a
    marked span with ``copy.indexOf(annotation.quote)`` and silently drops what it
    cannot find, so a paraphrase here is an annotation that never appears.
    """

    ref: int
    quote: str
    note: str
    determination: Determination


@dataclass(frozen=True, slots=True)
class Signal:
    """A measured reading. ``weight`` is 0–1 and sets the bar length."""

    label: str
    reading: str
    weight: float


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One counted fact, for the band of figures at the head of a record."""

    key: str
    value: str


@dataclass(frozen=True, slots=True)
class Exhibit:
    """A source the fact-check desk found, including the ones that disagree.

    ``relevance`` and ``reliability`` are separate axes on purpose: a highly
    reliable source can be barely relevant, and a directly relevant one can be
    unreliable. Collapsing them into a single score would hide exactly the case a
    reader needs to see.
    """

    ref: int
    source: str
    published: str
    relevance: Relevance
    reliability: Reliability
    determination: Determination
    extract: str


@dataclass(frozen=True, slots=True)
class PlateRegion:
    """A rectangle on an examined image, in percentages of the image box.

    Percentages rather than pixels because the reader that renders these scales
    the image to fit its frame — a pixel offset would line up at exactly one zoom
    level. ``ref`` is the annotation this region belongs to, or 0 for a region
    that was read but produced no claim.
    """

    ref: int
    x: float
    y: float
    w: float
    h: float
    label: str


@dataclass(frozen=True, slots=True)
class ImageDetail:
    """The image desk's own exhibit: what was on the page, and where.

    ``text`` is the recovered text as the pipeline received it, kept so a reader
    can see what the claims were extracted *from* — a verdict on text nobody can
    check against the picture is not reviewable.
    """

    width: int
    height: int
    text: str
    regions: tuple[PlateRegion, ...] = ()


@dataclass(frozen=True, slots=True)
class TranscriptCue:
    """One line of transcript, timed in seconds from the start of the clip.

    No speaker field. There is no diarization in this pipeline, and a label reading
    "Speaker 1" invites a reader to attribute a sentence to a person nobody
    identified. What was said and when is what was actually established.
    """

    ref: int
    start: float
    end: float
    text: str


@dataclass(frozen=True, slots=True)
class AudioDetail:
    """The audio desk's own exhibit: the waveform, and what was heard in it.

    ``envelope`` is one peak per bucket, each 0–1, for drawing a waveform; it says
    nothing about content. ``spans`` are the stretches the signal analysis found
    loud enough to be speech, as fractions of ``duration``, so a reader can see that
    a quoted line sits over sound rather than over silence.
    """

    duration: float
    language: str
    text: str
    envelope: tuple[float, ...] = ()
    spans: tuple[tuple[float, float], ...] = ()
    cues: tuple[TranscriptCue, ...] = ()


@dataclass(frozen=True, slots=True)
class Verdict:
    """A desk's closing finding, or the adjudicator's signed determination.

    ``confidence`` is a number in 0–1 and it is the authoritative form. The wire
    also publishes it as a formatted string because the frontend prints it inline,
    but a domain verdict holding only ``"92%"`` could not be thresholded, sorted or
    weighted without re-parsing the API's own output — and weighing the desks by
    how firmly each found what it found is the adjudicator's entire job.
    """

    determination: Determination
    headline: str
    rationale: str
    confidence: float

    def __post_init__(self) -> None:
        """Reject a confidence outside 0–1.

        Cheap, and it catches the one mistake this field invites: passing ``92``
        for ninety-two percent. A frozen dataclass has no validators, so this is
        the only place the range can be enforced.
        """
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence must be between 0 and 1, got {self.confidence!r}"
            )


@dataclass(frozen=True, slots=True)
class DeskReport:
    """What one desk returns.

    These five parts are what every desk has in common — they are the frontend's
    ``RecordBase`` plus the two collections that more than one desk fills. Each
    desk *also* produces one exhibit peculiar to itself: the plate's regions, the
    slate's envelope and transcript, the strip's frames and scenes.

    Those arrive as the optional ``detail`` field, discriminated on ``desk``, as
    each desk is built — the image desk fills it with an :class:`ImageDetail`, the
    audio desk with an :class:`AudioDetail`, and the union widens as later desks
    land. Adding an optional field is not a breaking change, which is what let this
    shape ship before any desk did.
    """

    desk: Desk
    verdict: Verdict
    ledger: tuple[LedgerEntry, ...] = ()
    annotations: tuple[Annotation, ...] = ()
    signals: tuple[Signal, ...] = ()
    exhibits: tuple[Exhibit, ...] = ()
    detail: ImageDetail | AudioDetail | None = None


@dataclass(frozen=True, slots=True)
class Failure:
    """Why a verification, or one desk within it, did not complete.

    Carries the ``code`` from :mod:`app.core.errors` rather than a free-text
    reason, so a client can branch on a failed verification the same way it
    branches on a failed request.
    """

    code: str
    message: str
    #: The desk that failed, when the failure is attributable to one.
    desk: Desk | None = None


@dataclass(frozen=True, slots=True)
class DeskProgress:
    """One desk's place in an examination.

    This is what makes polling worth doing. Without it a client watching a
    multi-desk job knows only that the whole thing is "running", and the stage
    ticker on the investigate page has to invent its own pacing from a hardcoded
    latency constant.
    """

    desk: Desk
    status: Status = Status.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Verification:
    """An examination: what was submitted, which desks were asked, what they found.

    Created ``PENDING``. Every subsequent state is reached through one of the
    transition methods below, each of which stamps ``updated_at`` — so "when did
    this last change" is never a question the caller has to remember to answer.

    There is no top-level ``verdict`` field. The adjudicator's report carries the
    signed verdict, and a copy here would give a reader two sources for one
    string; :attr:`verdict` reads it back out of the reports instead.
    """

    id: str
    artifact: Artifact
    desks: tuple[DeskProgress, ...]
    #: The account that submitted this, or ``None`` for an anonymous submission.
    #: Nullable by design: an artifact can be checked without an account, and the
    #: field is what the ownership rule in
    #: :meth:`app.services.verification.VerificationService.get` reads.
    user_id: str | None = None
    status: Status = Status.PENDING
    reports: tuple[DeskReport, ...] = ()
    failure: Failure | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    completed_at: datetime | None = None

    # ------------------------------------------------------------ building ---

    @classmethod
    def submitted(
        cls,
        *,
        artifact: Artifact,
        desks: tuple[Desk, ...],
        user_id: str | None = None,
    ) -> Verification:
        """Build a newly submitted verification with a fresh id.

        ``desks`` is the examining roster; the adjudicator is appended here rather
        than by the caller, because every verification ends with one and a caller
        that had to remember would eventually forget.
        """
        roster = (*desks, ADJUDICATOR)
        return cls(
            id=new_id(),
            artifact=artifact,
            desks=tuple(DeskProgress(desk=desk) for desk in roster),
            user_id=user_id,
        )

    # ------------------------------------------------------------- reading ---

    @property
    def verdict(self) -> Verdict | None:
        """The signed determination, once the adjudicator has reported."""
        for report in self.reports:
            if report.desk is ADJUDICATOR:
                return report.verdict
        return None

    @property
    def examining_desks(self) -> tuple[Desk, ...]:
        """The roster without the adjudicator, in running order."""
        return tuple(p.desk for p in self.desks if p.desk is not ADJUDICATOR)

    def report_for(self, desk: Desk) -> DeskReport | None:
        """The report ``desk`` filed, if it has filed one."""
        return next((r for r in self.reports if r.desk is desk), None)

    # --------------------------------------------------------- transitions ---

    def started(self) -> Verification:
        """Mark the examination as under way."""
        return replace(self, status=Status.RUNNING, updated_at=utcnow())

    def desk_started(self, desk: Desk) -> Verification:
        """Mark one desk as reading."""
        moment = utcnow()
        return self._with_desk(
            desk, status=Status.RUNNING, started_at=moment, moment=moment
        )

    def with_report(self, report: DeskReport) -> Verification:
        """File one desk's report and mark that desk done.

        The two go together: a desk that produced a report has finished, and
        letting a caller do one without the other is how a record ends up holding
        a report from a desk it still believes is reading.
        """
        moment = utcnow()
        return replace(
            self._with_desk(
                report.desk,
                status=Status.COMPLETED,
                completed_at=moment,
                moment=moment,
            ),
            reports=(*self.reports, report),
        )

    def completed(self) -> Verification:
        """Close the record. Every desk that was going to report has."""
        moment = utcnow()
        return replace(
            self,
            status=Status.COMPLETED,
            failure=None,
            updated_at=moment,
            completed_at=moment,
        )

    def failed(self, failure: Failure) -> Verification:
        """Record that the examination could not be completed.

        Any reports gathered before the failure are kept: three desks that
        reported and one that broke is more useful to a reader than nothing, and
        it is how a partial record gets shown rather than discarded. When the
        failure names a desk, that desk is marked failed too, so a reader can see
        which one stopped.
        """
        moment = utcnow()
        record = self
        if failure.desk is not None:
            record = record._with_desk(
                failure.desk,
                status=Status.FAILED,
                completed_at=moment,
                moment=moment,
            )
        return replace(
            record,
            status=Status.FAILED,
            failure=failure,
            updated_at=moment,
            completed_at=moment,
        )

    # ------------------------------------------------------------- private ---

    def _with_desk(
        self,
        desk: Desk,
        *,
        moment: datetime,
        status: Status,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> Verification:
        """Return a copy with one desk's progress replaced.

        A desk not on the roster is ignored rather than raising: the roster is
        fixed at submission, so this can only happen if a desk reported without
        being asked, and losing the progress row is preferable to losing the
        report that came with it.
        """
        updated = tuple(
            replace(
                progress,
                status=status,
                started_at=started_at or progress.started_at,
                completed_at=completed_at or progress.completed_at,
            )
            if progress.desk is desk
            else progress
            for progress in self.desks
        )
        return replace(self, desks=updated, updated_at=moment)
