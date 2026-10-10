"""Request and response shapes for verifications.

Two directions, and they are not symmetrical. Inbound, an artifact is a
discriminated union so that a submission is validated against the one shape it
claims to be. Outbound, everything is a flat record built by a ``from_domain``
classmethod from :mod:`app.domain`, so the wire format can change without a
service noticing.

Field names are snake_case, and there is no ``alias_generator`` here or anywhere
else in this package — see the note in :mod:`app.schemas`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    TypeAdapter,
)

from app.domain import (
    Annotation,
    Artifact,
    ArtifactKind,
    Desk,
    DeskProgress,
    DeskReport,
    Determination,
    Exhibit,
    Failure,
    ImageDetail,
    LedgerEntry,
    PlateRegion,
    Relevance,
    Reliability,
    Signal,
    Status,
    Verdict,
    Verification,
    desks_for,
)

_URL_ADAPTER = TypeAdapter(HttpUrl)


def _valid_url(value: str) -> str:
    """Validate ``value`` as an HTTP URL and return it exactly as submitted.

    ``HttpUrl`` does the checking but its parsed object never escapes this
    function. Two reasons: it is a pydantic ``Url``, not a ``str``, so passing it
    on would put pydantic underneath :mod:`app.domain`; and it normalises, and
    whether ``https://example.com`` gains a trailing slash has changed within the
    supported pydantic range — which would make the URL echoed back by
    ``GET /verification/{id}`` depend on the installed patch version.
    """
    _URL_ADAPTER.validate_python(value)
    return value


#: A URL that has been validated as one, carried as the caller's own string.
UrlString = Annotated[
    str,
    AfterValidator(_valid_url),
    Field(json_schema_extra={"format": "uri"}),
]


def format_confidence(value: float) -> str:
    """Render a 0–1 confidence the way a record prints it.

    One function so that the printed form is decided once. The frontend renders
    ``Confidence {verdict.confidence}`` inline and pushes the same string into a
    ledger row, so this is a published format rather than a debugging convenience.
    """
    return f"{round(value * 100)}%"


def format_timecode(seconds: float) -> str:
    """Render a position in a recording the way a record prints it.

    ``m:ss`` below an hour and ``h:mm:ss`` above it, which is how a reader writes a
    timestamp and not how a machine does. The seconds are published alongside for
    anything that needs to compute; see :class:`TranscriptCueOut`.
    """
    whole = int(max(0.0, seconds))
    minutes, remainder = divmod(whole, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{remainder:02d}"
    return f"{minutes}:{remainder:02d}"


# ============================================================== requests ====


class _ArtifactIn(BaseModel):
    """Base of the submitted-artifact union.

    Each member converts itself, and no ``to_domain`` is declared here on purpose.
    Every member of the union having the method is what makes
    ``self.artifact.to_domain()`` type-check, so a member added without one is a type
    error at the call site rather than a ``NotImplementedError`` at runtime.

    The alternative to per-member conversion — one function reading
    ``getattr(artifact, "content", None)`` across the union — would put the field
    names back into strings and let a new member's new field be silently dropped,
    which is the exact failure a discriminated union exists to prevent.
    """

    model_config = ConfigDict(extra="forbid")


class TextArtifactIn(_ArtifactIn):
    """Prose to be read: an article, a post, a transcript."""

    kind: Literal["text"]
    content: str = Field(
        min_length=1,
        description="The copy to examine. Upper bound is MAX_TEXT_CHARS.",
    )

    def to_domain(self) -> Artifact:
        return Artifact(kind=ArtifactKind.TEXT, content=self.content)


class ClaimArtifactIn(_ArtifactIn):
    """A single checkable assertion, already isolated from its prose."""

    kind: Literal["claim"]
    content: str = Field(
        min_length=1,
        description="One assertion, written to stand on its own.",
    )

    def to_domain(self) -> Artifact:
        return Artifact(kind=ArtifactKind.CLAIM, content=self.content)


class UrlArtifactIn(_ArtifactIn):
    """A link to fetch and read as copy."""

    kind: Literal["url"]
    url: UrlString = Field(description="Where the copy can be read.")

    def to_domain(self) -> Artifact:
        return Artifact(kind=ArtifactKind.URL, url=self.url)


class MediaArtifactIn(_ArtifactIn):
    """An image, a recording, or footage, referenced by URL.

    One model for three kinds because the fields are identical; a multi-value
    ``Literal`` is a legal discriminator member, and the OpenAPI document simply
    points three tags at this one schema.

    Media arrives by URL rather than as a file upload. Upload is multipart, needs
    ``MAX_UPLOAD_BYTES`` enforced against a stream, and is listed as not built.
    """

    kind: Literal["image"]
    url: UrlString = Field(description="Where the artifact can be fetched.")
    content: str | None = Field(
        default=None, max_length=5000, description="Caption or context to fact-check."
    )
    filename: str | None = Field(
        default=None,
        description="Original file name, if there was one. Printed, not parsed.",
    )

    def to_domain(self) -> Artifact:
        return Artifact(
            kind=ArtifactKind(self.kind),
            url=self.url,
            filename=self.filename,
            content=self.content,
        )


#: An artifact as submitted. Discriminated on ``kind``, which is what makes a
#: malformed submission produce one error naming the tag it failed to match rather
#: than one error per member of the union.
ArtifactIn = Annotated[
    TextArtifactIn | ClaimArtifactIn | UrlArtifactIn | MediaArtifactIn,
    Field(discriminator="kind"),
]

#: A requested roster. The constraints sit on ``list[Desk]`` inside the optional
#: rather than on ``list[Desk] | None``: metadata on the union would be applied to
#: the nullable wrapper, which is not a length-constrainable schema.
RequestedDesks = Annotated[list[Desk], Field(min_length=1, max_length=len(Desk))]


class VerifyRequest(BaseModel):
    """Body of ``POST /verify``."""

    model_config = ConfigDict(extra="forbid")

    artifact: ArtifactIn
    desks: RequestedDesks | None = Field(
        default=None,
        description=(
            "Which desks should open on the artifact. Omit to use the default "
            "roster for the artifact's kind. The decision desk cannot be named: "
            "it reads the other desks' records and is always added."
        ),
    )

    def to_domain(self) -> tuple[Artifact, tuple[Desk, ...]]:
        """Convert to the artifact and the resolved examining roster.

        The roster is resolved here, at the edge, so an unusable combination is a
        422 before anything is persisted. The rule itself lives in
        :func:`app.domain.desks_for` rather than in this model, so a worker or a
        script gets identical defaults and identical rejection.

        Why this is a method and not a ``model_validator``: ``desks_for`` reports a
        rejection with ``{desk, artifact_kind, allowed_desks}`` in ``details``, and
        pydantic cannot carry that. Pydantic converts only ``ValueError`` and
        ``AssertionError`` raised inside a validator, and the error it builds from
        one has no structured slot that survives — the details would flatten into
        prose. Raised from here instead, the ``VeritasError`` reaches the handler
        registered in :mod:`app.core.exception_handlers`, which renders the same 422
        in the same envelope with the details intact.
        """
        artifact = self.artifact.to_domain()
        return artifact, desks_for(artifact.kind, self.desks)


# ============================================================= responses ====


class ArtifactOut(BaseModel):
    """The artifact as submitted, echoed back on the record."""

    model_config = ConfigDict(extra="forbid")

    kind: ArtifactKind
    content: str | None = None
    url: str | None = None
    filename: str | None = None

    @classmethod
    def from_domain(cls, artifact: Artifact) -> Self:
        return cls(
            kind=artifact.kind,
            content=artifact.content,
            url=artifact.url,
            filename=artifact.filename,
        )


class VerdictOut(BaseModel):
    """A closing finding.

    ``confidence`` is the printed string and ``confidence_value`` the number it
    was rendered from. Both, because the two have different consumers: a record
    prints the string, and anything that wants to threshold, sort or weigh by
    confidence needs the number and should not have to parse the API's own output
    to get it. The pairing follows :class:`SignalOut`, which already carries a
    ``reading`` beside a ``weight``.
    """

    model_config = ConfigDict(extra="forbid")

    determination: Determination
    headline: str
    rationale: str
    confidence: str = Field(description='Printed form, e.g. "92%".')
    confidence_value: float = Field(ge=0.0, le=1.0, description="The same, as 0–1.")

    @classmethod
    def from_domain(cls, verdict: Verdict) -> Self:
        return cls(
            determination=verdict.determination,
            headline=verdict.headline,
            rationale=verdict.rationale,
            confidence=format_confidence(verdict.confidence),
            confidence_value=verdict.confidence,
        )


class AnnotationOut(BaseModel):
    """A note anchored to an exact span of the artifact."""

    model_config = ConfigDict(extra="forbid")

    ref: int
    quote: str = Field(description="Verbatim from the artifact, so it can be located.")
    note: str
    determination: Determination

    @classmethod
    def from_domain(cls, annotation: Annotation) -> Self:
        return cls(
            ref=annotation.ref,
            quote=annotation.quote,
            note=annotation.note,
            determination=annotation.determination,
        )


class SignalOut(BaseModel):
    """A measured reading, with the bar length that goes with it."""

    model_config = ConfigDict(extra="forbid")

    label: str
    reading: str
    weight: float = Field(ge=0.0, le=1.0)

    @classmethod
    def from_domain(cls, signal: Signal) -> Self:
        return cls(label=signal.label, reading=signal.reading, weight=signal.weight)


class LedgerEntryOut(BaseModel):
    """One counted fact from the head of a record."""

    model_config = ConfigDict(extra="forbid")

    key: str
    value: str

    @classmethod
    def from_domain(cls, entry: LedgerEntry) -> Self:
        return cls(key=entry.key, value=entry.value)


class ExhibitOut(BaseModel):
    """A source found on the record, including the ones that disagree."""

    model_config = ConfigDict(extra="forbid")

    ref: int
    source: str
    published: str
    relevance: Relevance
    reliability: Reliability
    determination: Determination
    extract: str
    url: str = ""
    claim_ref: int | None = None

    @classmethod
    def from_domain(cls, exhibit: Exhibit) -> Self:
        return cls(
            ref=exhibit.ref,
            source=exhibit.source,
            published=exhibit.published,
            relevance=exhibit.relevance,
            reliability=exhibit.reliability,
            determination=exhibit.determination,
            extract=exhibit.extract,
            url=exhibit.url,
            claim_ref=exhibit.claim_ref,
        )


class PlateRegionOut(BaseModel):
    """A rectangle on an examined image, as percentages of the image box."""

    model_config = ConfigDict(extra="forbid")

    ref: int
    x: float
    y: float
    w: float
    h: float
    label: str

    @classmethod
    def from_domain(cls, region: PlateRegion) -> Self:
        return cls(
            ref=region.ref,
            x=region.x,
            y=region.y,
            w=region.w,
            h=region.h,
            label=region.label,
        )


class ImageDetailOut(BaseModel):
    """The image desk's exhibit: what was read off the page, and where."""

    model_config = ConfigDict(extra="forbid")

    width: int
    height: int
    text: str
    regions: list[PlateRegionOut] = Field(default_factory=list)
    description: str = ""
    observations: list[str] = Field(default_factory=list)
    provenance: str = ""
    web_status: str = "not_searched"
    limitations: list[str] = Field(default_factory=list)
    metadata: list[LedgerEntryOut] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, detail: ImageDetail) -> Self:
        return cls(
            width=detail.width,
            height=detail.height,
            text=detail.text,
            regions=[PlateRegionOut.from_domain(r) for r in detail.regions],
            description=detail.description,
            observations=list(detail.observations),
            provenance=detail.provenance,
            web_status=detail.web_status,
            limitations=list(detail.limitations),
            metadata=[LedgerEntryOut.from_domain(e) for e in detail.metadata],
        )


class DeskReportOut(BaseModel):
    """What one desk filed.

    These are the parts every desk has in common. Each desk also produces one
    exhibit peculiar to itself — the plate's regions, the slate's transcript, the
    strip's frames — which arrives in ``detail``, discriminated on ``desk``, as
    each desk is built. The image desk fills it today; a client should
    tolerate unfamiliar shapes there rather than assume the union is closed.
    """

    model_config = ConfigDict(extra="forbid")

    desk: Desk
    verdict: VerdictOut
    ledger: list[LedgerEntryOut] = Field(default_factory=list)
    annotations: list[AnnotationOut] = Field(default_factory=list)
    signals: list[SignalOut] = Field(default_factory=list)
    exhibits: list[ExhibitOut] = Field(default_factory=list)
    detail: ImageDetailOut | None = None

    @classmethod
    def from_domain(cls, report: DeskReport) -> Self:
        return cls(
            desk=report.desk,
            verdict=VerdictOut.from_domain(report.verdict),
            ledger=[LedgerEntryOut.from_domain(e) for e in report.ledger],
            annotations=[AnnotationOut.from_domain(a) for a in report.annotations],
            signals=[SignalOut.from_domain(s) for s in report.signals],
            exhibits=[ExhibitOut.from_domain(e) for e in report.exhibits],
            detail=_detail(report.detail),
        )


def _detail(
    detail: ImageDetail | None,
) -> ImageDetailOut | None:
    """Dispatched on the domain type, not on ``report.desk``.

    Pydantic resolves a union by trying its members in order, and both shapes
    forbid extras, so it would in fact pick correctly. Doing it here means a desk
    filing a detail of the wrong shape fails at the boundary rather than being
    coerced into whichever member happens to validate.
    """
    if isinstance(detail, ImageDetail):
        return ImageDetailOut.from_domain(detail)
    return None


class DeskProgressOut(BaseModel):
    """Where one desk has got to.

    This is what makes polling worth doing: without it, a client watching a
    multi-desk examination knows only that the whole thing is running.
    """

    model_config = ConfigDict(extra="forbid")

    desk: Desk
    status: Status
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def from_domain(cls, progress: DeskProgress) -> Self:
        return cls(
            desk=progress.desk,
            status=progress.status,
            started_at=progress.started_at,
            completed_at=progress.completed_at,
        )


class FailureOut(BaseModel):
    """Why an examination stopped.

    Named ``failure`` on the record, never ``error``: ``error`` is the top-level key
    of every non-2xx body this API returns, and a 200 carrying one would leave a
    client unable to tell a failed verification from a failed request by shape.
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="Same vocabulary as the error envelope's `code`.")
    message: str
    desk: Desk | None = Field(
        default=None, description="The desk that stopped, when one is to blame."
    )

    @classmethod
    def from_domain(cls, failure: Failure) -> Self:
        return cls(code=failure.code, message=failure.message, desk=failure.desk)


class VerificationAccepted(BaseModel):
    """Body of the 202 from ``POST /verify``.

    Deliberately small. It confirms what was accepted and gives the id to poll;
    the record itself is read from ``GET /verification/{id}``, whose URL is also in
    the ``Location`` header.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    status: Status
    desks: list[Desk] = Field(description="The full roster, adjudicator included.")
    created_at: datetime

    @classmethod
    def from_domain(cls, record: Verification) -> Self:
        return cls(
            id=record.id,
            status=record.status,
            desks=[p.desk for p in record.desks],
            created_at=record.created_at,
        )


class VerificationOut(BaseModel):
    """The full record, from ``GET /verification/{id}``.

    There is no top-level ``verdict``. The decision desk's report carries the
    signed determination, and publishing a second copy here would give a reader two
    sources for one string with nothing deciding which wins.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    status: Status
    terminal: bool = Field(
        description="True when polling can stop: the status will not change again."
    )
    artifact: ArtifactOut
    desks: list[DeskProgressOut] = Field(
        description="The roster and each desk's progress, in running order."
    )
    reports: list[DeskReportOut] = Field(
        default_factory=list,
        description="Filed reports, in running order, the decision report last.",
    )
    failure: FailureOut | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    @classmethod
    def from_domain(cls, record: Verification) -> Self:
        return cls(
            id=record.id,
            status=record.status,
            terminal=record.status.is_terminal,
            artifact=ArtifactOut.from_domain(record.artifact),
            desks=[DeskProgressOut.from_domain(p) for p in record.desks],
            reports=[DeskReportOut.from_domain(r) for r in record.reports],
            failure=(
                FailureOut.from_domain(record.failure) if record.failure else None
            ),
            created_at=record.created_at,
            updated_at=record.updated_at,
            completed_at=record.completed_at,
        )


class VerificationSummaryOut(BaseModel):
    """One row of ``GET /verifications``.

    A record without its reports. The signed verdict is here because it is what a
    list is read for; the desk reports are not, because each carries its annotations,
    signals and exhibits, and twenty of those is a response nobody asked for to
    render a list of twenty lines. A row's ``id`` fetches the full record.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    status: Status
    terminal: bool
    artifact: ArtifactOut
    verdict: VerdictOut | None = Field(
        default=None,
        description="The signed determination, once the decision desk has reported.",
    )
    failure: FailureOut | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    @classmethod
    def from_domain(cls, record: Verification) -> Self:
        verdict = record.verdict
        return cls(
            id=record.id,
            status=record.status,
            terminal=record.status.is_terminal,
            artifact=ArtifactOut.from_domain(record.artifact),
            verdict=VerdictOut.from_domain(verdict) if verdict else None,
            failure=(
                FailureOut.from_domain(record.failure) if record.failure else None
            ),
            created_at=record.created_at,
            updated_at=record.updated_at,
            completed_at=record.completed_at,
        )


class VerificationHistoryOut(BaseModel):
    """The caller's own verifications, from ``GET /verifications``.

    An object rather than a bare array. A top-level JSON array cannot gain a field,
    so the paging this will eventually need would be a breaking change; ``count`` is
    the count of ``items`` and not a total, because nothing here counts rows the
    query did not return.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[VerificationSummaryOut]
    count: int = Field(description="How many rows are in `items`.")

    @classmethod
    def from_domain(cls, records: Sequence[Verification]) -> Self:
        return cls(
            items=[VerificationSummaryOut.from_domain(r) for r in records],
            count=len(records),
        )
