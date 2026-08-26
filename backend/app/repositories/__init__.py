"""Persistence, behind a Protocol.

One module per implementation beside a ``base.py`` holding the contract, which is
how all four provider seams in this application are laid out. Services depend on
:class:`app.repositories.base.VerificationRepository` and never on the class that
implements it, so which store is running is decided in one place — the
``VERIFICATION_STORE`` setting, read by :func:`app.main.create_app` — and no service,
route or test changes when it moves.

Two implementations of the verification contract ship: the in-memory store, which
is single-process and bounded, and the SQLAlchemy one in
:mod:`app.repositories.sql`, which is the durable one. Accounts have both too, so
authentication works under ``VERIFICATION_STORE=memory`` — a suite that had to run
PostgreSQL to test a login would not be run. Research has only the SQL
implementation; there was never an in-memory version of it to keep.
"""

from __future__ import annotations

from app.repositories.base import (
    ResearchRepository,
    UserRepository,
    VerificationRepository,
)
from app.repositories.memory import (
    MAX_RECORDS,
    InMemoryUserRepository,
    InMemoryVerificationRepository,
)
from app.repositories.sql import (
    SqlResearchRepository,
    SqlUserRepository,
    SqlVerificationRepository,
)

__all__ = [
    "MAX_RECORDS",
    "InMemoryUserRepository",
    "InMemoryVerificationRepository",
    "ResearchRepository",
    "SqlResearchRepository",
    "SqlUserRepository",
    "SqlVerificationRepository",
    "UserRepository",
    "VerificationRepository",
]
