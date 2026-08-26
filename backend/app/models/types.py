"""Column primitives shared by every table.

Four decisions made once here so the model modules do not each make them
differently. Each is a place where the obvious SQLAlchemy default is wrong for
this application, which is why this module exists instead of the models reaching
for ``mapped_column`` unaided.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, String, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

#: Length of a UUID4 in canonical string form. Ids are stored as text rather than
#: in a native ``Uuid`` column because the repository contract lets a caller read
#: *any* string id — ``get("nope")`` must answer ``None``, not raise — and a native
#: column rejects a malformed UUID before the store gets to answer at all.
ID_LENGTH = 36


def id_column() -> String:
    return String(ID_LENGTH)


def enum_column(enum: type[StrEnum], *, name: str) -> Enum:
    """A CHECK-constrained text column holding a :class:`StrEnum` by *value*.

    ``values_callable`` is the load-bearing argument. Without it SQLAlchemy
    persists the member *name*, so ``Desk.FACT_CHECK`` would land in the database
    as ``FACT_CHECK`` while every other layer — routes, schemas, the frontend —
    speaks its value, ``fact-check``. A row written by one and matched by the other
    would then never be found.

    ``native_enum=False`` keeps this a ``VARCHAR`` with a CHECK rather than a
    PostgreSQL ``ENUM`` type, so adding a determination is an ordinary constraint
    change instead of an ``ALTER TYPE`` that cannot run inside a transaction.
    """
    return Enum(
        enum,
        name=name,
        native_enum=False,
        values_callable=_enum_values,
        length=max(len(value) for value in _enum_values(enum)),
    )


def _enum_values(enum: type[StrEnum]) -> list[str]:
    return [str(member) for member in enum]


def json_column() -> JSON:
    """JSON everywhere, JSONB on PostgreSQL.

    The still-settling interior of a desk report — ledger, annotations, signals,
    exhibits — and the research satellites are documents rather than columns, and
    pinning them to columns now would mean a migration every time one gains a
    field. The variant is what lets the same metadata build on SQLite, which is
    what the repository tests run against.

    A fresh instance per call: a type carrying a dialect variant belongs to the
    column that uses it, and sharing one instance across tables couples their DDL.
    """
    return JSON().with_variant(JSONB(), "postgresql")


class UTCDateTime(TypeDecorator[datetime]):
    """A timestamp that stays timezone-aware across a backend that is not.

    PostgreSQL round-trips the offset. SQLite discards it and returns a naive
    datetime, which then compares unequal to the aware value that went in — so a
    repository verified on one and deployed on the other would disagree about
    ``created_at`` without any code changing. UTC is re-attached on the way out.

    Nothing in the domain holds a naive datetime, so a naive value arriving on the
    way *in* is a bug above this layer; it is stamped UTC rather than guessed at,
    which keeps the column consistent instead of storing a local time as if it were
    universal.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Any
    ) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    def process_result_value(
        self, value: datetime | None, dialect: Any
    ) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
