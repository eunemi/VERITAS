"""Database engine and session management.

The engine is created lazily and held at module scope, because an async engine
owns a connection pool and there must be exactly one per process. It is created
on first use rather than at import time so that importing any part of the
application — in a test, in a CLI script — does not open sockets.

Swapping PostgreSQL for something else is a change to ``DATABASE_URL`` plus a
driver in ``requirements.txt``. Nothing above this module names PostgreSQL.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _clean_database_url(raw_url: str) -> tuple[str, dict[str, Any]]:
    """Sanitize database URL and resolve driver-specific connection arguments."""
    url = make_url(raw_url)
    connect_args: dict[str, Any] = {}

    if "postgresql" in url.get_backend_name():
        query_dict = dict(url.query)
        has_ssl = False
        if "sslmode" in query_dict:
            val = query_dict.pop("sslmode")
            if val in ("require", "verify-ca", "verify-full"):
                has_ssl = True
        if "channel_binding" in query_dict:
            query_dict.pop("channel_binding")
        if "ssl" in query_dict:
            val = query_dict.pop("ssl")
            if str(val).lower() in ("true", "1", "require"):
                has_ssl = True

        if (url.host and url.host not in ("localhost", "127.0.0.1", "postgres")) or has_ssl:
            connect_args["ssl"] = True

        url = url.set(query=query_dict)

    return url.render_as_string(hide_password=False), connect_args


def _create_engine(settings: Settings) -> AsyncEngine:
    clean_url, connect_args = _clean_database_url(settings.DATABASE_URL)
    kwargs: dict[str, Any] = {
        "echo": settings.DATABASE_ECHO,
        "connect_args": connect_args,
    }

    # SQLite's async driver is backed by a pool that accepts none of the sizing
    # arguments below, and passing them raises at engine construction. Guarding
    # here is what makes this module's promise — that changing database is a URL
    # change — true for the one URL a developer is most likely to try locally.
    if make_url(clean_url).get_backend_name() != "sqlite":
        kwargs.update(
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            # Recycle before a typical cloud idle-connection timeout, and verify
            # a connection is alive before handing it out. Without these, the
            # first query after an idle period fails on a dropped socket.
            pool_recycle=1800,
            pool_pre_ping=True,
        )

    return create_async_engine(clean_url, **kwargs)


def get_engine() -> AsyncEngine:
    """Return the process-wide engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = _create_engine(get_settings())
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            # Attributes stay loaded after commit, so a handler can still read
            # from an object it just saved without triggering lazy IO.
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield a session for one unit of work.

    Used as a FastAPI dependency. The session is rolled back and closed on the
    way out; committing is the caller's decision, because only the caller knows
    where the transaction boundary is.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Close the pool. Called on application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        logger.info("database engine disposed")
    _engine = None
    _session_factory = None
