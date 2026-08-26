"""Time.

Every timestamp the application produces comes from here. The point is not
convenience — it is that ``utcnow`` is one function to substitute in a test, and
that nothing in the codebase reaches for the naive ``datetime.utcnow`` that
returns a timezone-unaware value.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``."""
    return datetime.now(UTC)


def isoformat(moment: datetime | None = None) -> str:
    """Return ``moment`` (default: now) as an ISO 8601 string in UTC."""
    return (moment or utcnow()).isoformat()
