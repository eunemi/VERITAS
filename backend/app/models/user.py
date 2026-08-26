"""The users table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models.types import UTCDateTime, id_column


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(id_column(), primary_key=True)
    # 320 is the longest address RFC 5321 allows: 64-char local part, 255-char
    # domain, one `@`. Unique on the normalised form the domain produces.
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
