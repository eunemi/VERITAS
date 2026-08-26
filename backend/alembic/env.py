"""Alembic environment.

Two things here are not the template's defaults, and both matter.

**The URL comes from the application's settings**, not from ``alembic.ini``. One
source for the connection string means ``alembic upgrade head`` cannot run against
a different database than the one the API is using.

**Migrations run through the async driver.** ``DATABASE_URL`` names ``asyncpg``, and
Alembic's runner is synchronous, so the connection is opened in an event loop and
the migration itself is handed to :meth:`AsyncConnection.run_sync`. Rewriting the
URL to a sync driver instead would need psycopg installed alongside asyncpg for no
other reason.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Importing the package is what populates `Base.metadata`; autogenerate compares
# against it, so a table whose module is not imported reads as one to be dropped.
import app.models  # noqa: F401
from alembic import context
from app.core.config import get_settings
from app.database.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL)

target_metadata = Base.metadata


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Without this a column changing from VARCHAR(64) to VARCHAR(80) produces
        # an empty revision, and the constraint that was supposed to widen does not.
        compare_type=True,
        compare_server_default=True,
        # Named constraints come from the convention in `app.database.base`;
        # rendering it here is what lets a batch operation drop one by name.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it, for review or a managed rollout."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
    )
    async with engine.connect() as connection:
        await connection.run_sync(_configure)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
