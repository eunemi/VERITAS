"""What the research produced: claims, the sources found for them, and the
evidence quoted out of those sources.

Three tables in a chain — a claim has sources, a source has evidence — because
those are the three things a reader asks for separately. "Which sources did this
claim rest on" and "what exactly did that source say" are both answerable with a
WHERE clause here; folded into one JSON document per claim they would not be.

What stays JSON is what nothing queries by: the retrievals behind a source (one
row per provider per query — audit trail, not a lookup key), the credibility
readings, and the fact-check reviews. Those are documents whose shape is still
moving, and a column each would mean a migration per field.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.domain import DateBasis
from app.models.types import (
    UTCDateTime,
    enum_column,
    id_column,
    json_column,
)


class ClaimRow(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(id_column(), primary_key=True)
    # Nullable: research runs on its own, from `WebResearchService`, and a dossier
    # built by a script or a worker has no verification to hang off. When there is
    # one, deleting it takes the research with it.
    verification_id: Mapped[str | None] = mapped_column(
        id_column(), ForeignKey("verifications.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    queries: Mapped[list[Any]] = mapped_column(json_column(), default=list)
    fact_checks: Mapped[list[Any]] = mapped_column(json_column(), default=list)
    researched_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)

    sources: Mapped[list[SourceRow]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        order_by="SourceRow.ref",
        lazy="selectin",
    )


class SourceRow(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(id_column(), primary_key=True)
    claim_id: Mapped[str] = mapped_column(
        id_column(), ForeignKey("claims.id", ondelete="CASCADE"), index=True
    )
    ref: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(Text)
    # Every URL that resolved to this source — the same story reached by two
    # providers under two links is one row, and the alternates are kept so a reader
    # can see which link each provider actually returned.
    urls: Mapped[list[Any]] = mapped_column(json_column(), default=list)
    title: Mapped[str] = mapped_column(Text, default="")
    # Indexed because credibility is scored per registrable domain, so "everything
    # this publisher was cited for" is a question the store gets asked directly.
    domain: Mapped[str] = mapped_column(String(255), index=True)
    host: Mapped[str] = mapped_column(String(255), default="")

    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    date_basis: Mapped[DateBasis | None] = mapped_column(
        enum_column(DateBasis, name="date_basis")
    )
    date_text: Mapped[str | None] = mapped_column(String(255))
    cluster: Mapped[int | None] = mapped_column(Integer)

    retrievals: Mapped[list[Any]] = mapped_column(json_column(), default=list)
    credibility: Mapped[dict[str, Any] | None] = mapped_column(json_column())

    claim: Mapped[ClaimRow] = relationship(back_populates="sources")
    evidence: Mapped[list[EvidenceRow]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        order_by="EvidenceRow.position",
        lazy="selectin",
    )


class EvidenceRow(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(id_column(), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        id_column(), ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(60))
    # `start` and `end` on the domain object; renamed here because END is a
    # reserved word in PostgreSQL and an unquoted column of that name will not
    # parse. The offsets locate the quote inside the retrieved text.
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)

    matched_entities: Mapped[list[Any]] = mapped_column(json_column(), default=list)
    matched_terms: Mapped[list[Any]] = mapped_column(json_column(), default=list)
    matched_numbers: Mapped[list[Any]] = mapped_column(json_column(), default=list)

    source: Mapped[SourceRow] = relationship(back_populates="evidence")
