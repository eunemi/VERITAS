"""The users store.

Ordinary CRUD, with one thing worth stating: nothing here hashes or checks a
password. ``password_hash`` is carried through as an opaque string because no
authentication is implemented — the JWT settings in :mod:`app.core.config` are
validated but unused, and no JWT library is installed. This store is what an auth
layer would be built on, not the auth layer.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import NotFoundError, ValidationError
from app.database.session import get_session_factory
from app.domain import User, normalise_email
from app.models import UserRow


class SqlUserRepository:
    """Stores accounts in PostgreSQL."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] | None = None
    ) -> None:
        self._session_factory = session_factory

    @property
    def _factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory or get_session_factory()

    async def create(self, user: User) -> None:
        async with self._factory() as session:
            session.add(_to_row(user))
            try:
                await session.commit()
            except IntegrityError as exc:
                # The unique index on `email` is the only constraint a caller can
                # trip here, and it is a 422 rather than a 500: the request was
                # well-formed, the address is simply taken. Reported without saying
                # whether the existing account is active, which would otherwise
                # make this endpoint an account-enumeration oracle.
                await session.rollback()
                raise ValidationError(
                    "That email address is already registered.",
                    details={"email": user.email},
                ) from exc

    async def get(self, user_id: str) -> User | None:
        async with self._factory() as session:
            row = await session.get(UserRow, user_id)
            return _to_domain(row) if row is not None else None

    async def get_by_email(self, email: str) -> User | None:
        async with self._factory() as session:
            found = await session.execute(
                select(UserRow).where(UserRow.email == normalise_email(email))
            )
            row = found.scalar_one_or_none()
            return _to_domain(row) if row is not None else None

    async def update(self, user: User) -> None:
        async with self._factory() as session:
            row = await session.get(UserRow, user.id)
            if row is None:
                raise NotFoundError(
                    f"No user with id {user.id}.", details={"user_id": user.id}
                )
            row.email = user.email
            row.display_name = user.display_name
            row.password_hash = user.password_hash
            row.is_active = user.is_active
            row.updated_at = user.updated_at
            await session.commit()


def _to_row(user: User) -> UserRow:
    return UserRow(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        password_hash=user.password_hash,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _to_domain(row: UserRow) -> User:
    return User(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        password_hash=row.password_hash,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
