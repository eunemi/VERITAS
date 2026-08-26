"""SQLAlchemy models.

One module per aggregate, each importing ``Base`` from :mod:`app.database.base`.
Every module is imported here because ``Base.metadata`` is only complete once they
all have been — Alembic's ``env.py`` and any ``create_all`` call read that metadata,
so a table whose module is never imported silently does not exist.

Mapped classes carry a ``Row`` suffix. Six of the seven would otherwise collide
with the identically-named frozen dataclass in :mod:`app.domain`, and a module that
imported both would have to alias one — which is exactly the confusion the suffix
avoids. The domain type is the one without the suffix, and it is the one the rest
of the application speaks; these classes exist only inside
:mod:`app.repositories.sql`.
"""

from __future__ import annotations

from app.models.research import ClaimRow, EvidenceRow, SourceRow
from app.models.types import (
    ID_LENGTH,
    UTCDateTime,
    enum_column,
    id_column,
    json_column,
)
from app.models.user import UserRow
from app.models.verification import DeskReportRow, DeskRow, VerificationRow

__all__ = [
    "ID_LENGTH",
    "ClaimRow",
    "DeskReportRow",
    "DeskRow",
    "EvidenceRow",
    "SourceRow",
    "UTCDateTime",
    "UserRow",
    "VerificationRow",
    "enum_column",
    "id_column",
    "json_column",
]
