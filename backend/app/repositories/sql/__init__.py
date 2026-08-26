"""SQLAlchemy implementations of the repository Protocols.

One module per aggregate, plus :mod:`app.repositories.sql.coding` for the
domain-to-JSON codec they share. Nothing outside this package imports
:mod:`app.models` or :mod:`sqlalchemy` on the persistence path — services hold a
Protocol, routes hold a service, and which store is in use is decided in one place
(:func:`app.main.create_app`). That is the whole point of the seam: the SQL is here,
and it is only here.
"""

from __future__ import annotations

from app.repositories.sql.research import SqlResearchRepository
from app.repositories.sql.users import SqlUserRepository
from app.repositories.sql.verifications import SqlVerificationRepository

__all__ = [
    "SqlResearchRepository",
    "SqlUserRepository",
    "SqlVerificationRepository",
]
