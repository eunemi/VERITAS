"""The verification aggregate: the request, its desk roster, and the filed reports.

Three tables, one file, because they are one aggregate — a verification is never
loaded without its desks and its reports, and the repository writes all three
through the same session. The report interior (ledger, annotations, signals,
exhibits, detail) is JSON rather than columns; see :mod:`app.repositories.sql.coding`
for why, and for the codec that reads it back into domain dataclasses.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.domain import ArtifactKind, Desk, Determination, Status
from app.models.types import (
    UTCDateTime,
    enum_column,
    id_column,
    json_column,
)


class VerificationRow(Base):
    __tablename__ = "verifications"

    id: Mapped[str] = mapped_column(id_column(), primary_key=True)
    # The owner is nullable and nulls on delete, not cascades: closing an account
    # must not erase the examinations it requested. See `app.domain.user`.
    user_id: Mapped[str | None] = mapped_column(
        id_column(), ForeignKey("users.id", ondelete="SET NULL")
    )

    artifact_kind: Mapped[ArtifactKind] = mapped_column(
        enum_column(ArtifactKind, name="artifact_kind")
    )
    artifact_content: Mapped[str | None] = mapped_column(Text)
    artifact_url: Mapped[str | None] = mapped_column(Text)
    artifact_filename: Mapped[str | None] = mapped_column(String(255))

    status: Mapped[Status] = mapped_column(enum_column(Status, name="status"))
    failure_code: Mapped[str | None] = mapped_column(String(80))
    failure_message: Mapped[str | None] = mapped_column(Text)
    failure_desk: Mapped[Desk | None] = mapped_column(
        enum_column(Desk, name="failure_desk")
    )

    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    # selectin, not lazy: async mappers cannot emit IO on attribute access, so the
    # children are fetched in a follow-up SELECT when the parent loads. Ordered so
    # the roster and the reports come back in running order without a sort upstream.
    desks: Mapped[list[DeskRow]] = relationship(
        back_populates="verification",
        cascade="all, delete-orphan",
        order_by="DeskRow.position",
        lazy="selectin",
    )
    reports: Mapped[list[DeskReportRow]] = relationship(
        back_populates="verification",
        cascade="all, delete-orphan",
        order_by="DeskReportRow.position",
        lazy="selectin",
    )


class DeskRow(Base):
    __tablename__ = "verification_desks"

    verification_id: Mapped[str] = mapped_column(
        id_column(),
        ForeignKey("verifications.id", ondelete="CASCADE"),
        primary_key=True,
    )
    desk: Mapped[Desk] = mapped_column(
        enum_column(Desk, name="desk"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[Status] = mapped_column(enum_column(Status, name="status"))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    verification: Mapped[VerificationRow] = relationship(back_populates="desks")


class DeskReportRow(Base):
    __tablename__ = "desk_reports"

    id: Mapped[str] = mapped_column(id_column(), primary_key=True)
    verification_id: Mapped[str] = mapped_column(
        id_column(), ForeignKey("verifications.id", ondelete="CASCADE")
    )
    # Deliberately no unique (verification_id, desk): the in-memory store lets a
    # desk file more than one report, and the two implementations must agree on
    # what is storable or the swap changes behaviour. The adjudicator's row here,
    # last in `position`, is the final result — there is no separate results table,
    # because a copy of the signed verdict would give a reader two sources for one
    # string (see `app.domain.verification`).
    desk: Mapped[Desk] = mapped_column(enum_column(Desk, name="desk"))
    position: Mapped[int] = mapped_column(Integer)

    determination: Mapped[Determination] = mapped_column(
        enum_column(Determination, name="determination")
    )
    headline: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)

    ledger: Mapped[list[Any]] = mapped_column(json_column(), default=list)
    annotations: Mapped[list[Any]] = mapped_column(json_column(), default=list)
    signals: Mapped[list[Any]] = mapped_column(json_column(), default=list)
    exhibits: Mapped[list[Any]] = mapped_column(json_column(), default=list)
    detail: Mapped[dict[str, Any] | None] = mapped_column(json_column())

    filed_at: Mapped[datetime] = mapped_column(UTCDateTime)

    verification: Mapped[VerificationRow] = relationship(back_populates="reports")
