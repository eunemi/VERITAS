"""The domain layer: what the application is about, in plain Python.

Frozen dataclasses and enums, no pydantic and no framework. Services, the desk
seam and the repository all speak these types; :mod:`app.schemas` converts them to
and from the wire. That split is why the same orchestration can be driven from a
worker or a script without importing FastAPI, which is the property the rest of
this codebase already maintains for ``app.core``, ``app.utils`` and the four
provider seams.

Dependencies point one way: this package imports :mod:`app.core.errors` and
:mod:`app.utils` and nothing else from the application. In particular it does not
import :mod:`app.desks` — the report types the seam returns are defined *here*,
which is what keeps the two from importing each other.

Import from this package, not from its modules — ``from app.domain import
Verification`` — so the internal file layout stays free to change.
"""

from __future__ import annotations

from app.domain.claims import (
    Entity,
    ExtractedClaim,
    Extraction,
    Keyword,
    Unfit,
)
from app.domain.credibility import (
    Axis,
    Band,
    Credibility,
    Direction,
    Observation,
    Reading,
    Role,
)
from app.domain.enums import (
    ADJUDICATOR,
    DEFAULT_DESKS,
    ArtifactKind,
    Desk,
    Determination,
    Relevance,
    Reliability,
    Status,
    can_examine,
    desks_for,
)
from app.domain.factcheck import (
    FactCheck,
    Review,
    ReviewedClaim,
    Stance,
)
from app.domain.research import (
    ClaimResearch,
    DateBasis,
    Dossier,
    Evidence,
    ProviderOutcome,
    ProviderStatus,
    Retrieval,
    SkippedClaim,
    Source,
)
from app.domain.user import User, normalise_email
from app.domain.verification import (
    Annotation,
    Artifact,
    AudioDetail,
    DeskProgress,
    DeskReport,
    Exhibit,
    Failure,
    ImageDetail,
    LedgerEntry,
    PlateRegion,
    Signal,
    TranscriptCue,
    Verdict,
    Verification,
)

__all__ = [
    "ADJUDICATOR",
    "DEFAULT_DESKS",
    "Annotation",
    "Artifact",
    "ArtifactKind",
    "AudioDetail",
    "Axis",
    "Band",
    "ClaimResearch",
    "Credibility",
    "DateBasis",
    "Desk",
    "DeskProgress",
    "DeskReport",
    "Determination",
    "Direction",
    "Dossier",
    "Entity",
    "Evidence",
    "Exhibit",
    "ExtractedClaim",
    "Extraction",
    "FactCheck",
    "Failure",
    "ImageDetail",
    "Keyword",
    "LedgerEntry",
    "Observation",
    "PlateRegion",
    "ProviderOutcome",
    "ProviderStatus",
    "Reading",
    "Relevance",
    "Reliability",
    "Retrieval",
    "Review",
    "ReviewedClaim",
    "Role",
    "Signal",
    "SkippedClaim",
    "Source",
    "Stance",
    "Status",
    "TranscriptCue",
    "Unfit",
    "User",
    "Verdict",
    "Verification",
    "can_examine",
    "desks_for",
    "normalise_email",
]
