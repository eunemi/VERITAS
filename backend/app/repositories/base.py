"""The persistence contracts.

Named for intent — ``mark_running``, ``add_report``, ``complete``, ``fail`` —
rather than a single ``save(verification)``. Two reasons, both about what replaces
this. A load-replace-overwrite interface makes every state change a read of the
whole record followed by a blind write, so two coroutines advancing the same
verification lose one of the two writes; and the SQLAlchemy implementation that
takes over from the in-memory one would have to fetch a row just to change a
status column. Naming the transitions means each is one statement in SQL later and
each is atomic in the store today.

Reads return ``None`` for an unknown id; they do not raise. Deciding that a
missing verification is a 404 is the service's job, because a worker asking the
same question wants an answer rather than an exception. Writes against an unknown
id *do* raise :class:`app.core.errors.NotFoundError` — silently discarding a
report would hide an orchestrator bug behind a record that merely looks unfinished.

These are Protocols, not base classes, and services annotate against them. That is
what makes the store a one-line choice in :func:`app.main.create_app`: nothing
above this module imports :mod:`app.repositories.sql`, so nothing above it imports
SQLAlchemy either.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain import (
    ClaimResearch,
    Desk,
    DeskReport,
    Dossier,
    Failure,
    User,
    Verification,
)


@runtime_checkable
class VerificationRepository(Protocol):
    """Stores verifications and advances their state."""

    async def create(self, verification: Verification) -> None:
        """Persist a newly submitted verification."""
        ...

    async def get(self, verification_id: str) -> Verification | None:
        """Return the verification, or ``None`` if there is no such id."""
        ...

    async def list_for_user(
        self, user_id: str, *, limit: int = 50
    ) -> tuple[Verification, ...]:
        """The verifications owned by ``user_id``, newest first.

        The owner is part of the query rather than a filter applied to its results.
        That is the difference between an implementation that cannot return
        somebody else's record and one that merely does not — and this is the
        method a history endpoint is built on, so it is the one place where the
        distinction decides whether the endpoint leaks.

        Anonymous verifications have no owner and are never returned here.
        """
        ...

    async def mark_running(self, verification_id: str) -> None:
        """Record that the examination has begun."""
        ...

    async def start_desk(self, verification_id: str, desk: Desk) -> None:
        """Record that ``desk`` has started reading."""
        ...

    async def add_report(self, verification_id: str, report: DeskReport) -> None:
        """File a desk's report, which also marks that desk finished."""
        ...

    async def complete(self, verification_id: str) -> None:
        """Close the record. The adjudicator has signed."""
        ...

    async def fail(self, verification_id: str, failure: Failure) -> None:
        """Record that the examination could not be completed.

        Whatever reports were already filed are kept.
        """
        ...


@runtime_checkable
class UserRepository(Protocol):
    """Stores accounts.

    No method takes or checks a password. ``User.password_hash`` is carried through
    opaque, and the hashing and comparison that produce it live in
    :mod:`app.security.passwords`, reached only through
    :class:`app.services.auth.AuthService`. A store that verified a password would
    be a store that could be asked to, from anywhere.
    """

    async def create(self, user: User) -> None:
        """Persist a new account.

        Raises :class:`app.core.errors.ValidationError` if the address is taken.
        """
        ...

    async def get(self, user_id: str) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None:
        """Look up by address, normalised the way registration normalises it."""
        ...

    async def update(self, user: User) -> None:
        """Write back a changed account. Raises ``NotFoundError`` for an unknown id."""
        ...


@runtime_checkable
class ResearchRepository(Protocol):
    """Stores what the research produced: claims, their sources, their evidence."""

    async def save_dossier(
        self, dossier: Dossier, *, verification_id: str | None = None
    ) -> tuple[str, ...]:
        """Persist every claim in the dossier and return their new ids, in order.

        ``verification_id`` is optional because research runs on its own —
        :class:`app.services.research.WebResearchService` is callable from a script
        with no verification anywhere near it.
        """
        ...

    async def get_research(self, claim_id: str) -> ClaimResearch | None: ...

    async def research_for(self, verification_id: str) -> tuple[ClaimResearch, ...]:
        """Every claim researched under one verification, in the order submitted."""
        ...
