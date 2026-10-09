"""In-memory stores for verifications and accounts.

Deliberately not a database. Both implement the Protocols in
:mod:`app.repositories.base` that the SQLAlchemy stores implement, so choosing them
is one line in :func:`app.main.create_app`.

**Single process only.** Records live in these objects' dicts, so two workers do not
see each other's verifications or each other's accounts, and a restart loses
everything — including every registration. That is what ``VERIFICATION_STORE=memory``
means, and it is why the default is the database.

Held on ``app.state``, never at module scope. The tests build a fresh application
per test through ``create_app``, so a module-level dict would carry records between
test cases and surface as order-dependent failures that are very hard to read.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict

from app.core.errors import NotFoundError, ValidationError
from app.domain import Desk, DeskReport, Failure, User, Verification, normalise_email

#: How many records to keep. A long-lived process serving a submit-then-poll API
#: would otherwise grow for its whole life, since nothing here expires and the
#: frontend's "Commission another" drops the previous record on the floor. The
#: oldest go first, so a client polling an id it submitted an hour and a thousand
#: verifications ago gets a 404 — correct, if blunt, and another reason this is not
#: the permanent store.
MAX_RECORDS = 1000


class InMemoryVerificationRepository:
    """Keeps verifications in an insertion-ordered dict, newest last."""

    def __init__(self, *, max_records: int = MAX_RECORDS) -> None:
        self._records: OrderedDict[str, Verification] = OrderedDict()
        self._max_records = max_records
        # Every mutator is read-modify-write. Nothing inside a critical section
        # awaits today, so the GIL alone would serialise them — but the lock is
        # what keeps that true the moment one of them does, and it documents that
        # these operations are meant to be atomic rather than accidentally so.
        self._lock = asyncio.Lock()

    async def create(self, verification: Verification) -> None:
        async with self._lock:
            self._records[verification.id] = verification
            while len(self._records) > self._max_records:
                self._records.popitem(last=False)

    async def get(self, verification_id: str) -> Verification | None:
        return self._records.get(verification_id)

    async def list_for_user(
        self, user_id: str, *, limit: int = 50
    ) -> tuple[Verification, ...]:
        # `record.user_id == user_id` and not a truthiness test: an anonymous record
        # holds None, and comparing it against an empty string must not match.
        owned = [r for r in self._records.values() if r.user_id == user_id]
        owned.reverse()
        return tuple(owned[:limit])

    async def mark_running(self, verification_id: str) -> None:
        async with self._lock:
            self._replace(verification_id, self._require(verification_id).started())

    async def start_desk(self, verification_id: str, desk: Desk) -> None:
        async with self._lock:
            self._replace(
                verification_id, self._require(verification_id).desk_started(desk)
            )

    async def add_report(self, verification_id: str, report: DeskReport) -> None:
        async with self._lock:
            self._replace(
                verification_id, self._require(verification_id).with_report(report)
            )

    async def complete(self, verification_id: str) -> None:
        async with self._lock:
            self._replace(verification_id, self._require(verification_id).completed())

    async def fail(self, verification_id: str, failure: Failure) -> None:
        async with self._lock:
            self._replace(
                verification_id, self._require(verification_id).failed(failure)
            )

    # ------------------------------------------------------------- private ---

    def _require(self, verification_id: str) -> Verification:
        record = self._records.get(verification_id)
        if record is None:
            raise NotFoundError(
                f"No verification with id {verification_id}.",
                details={"verification_id": verification_id},
            )
        return record

    def _replace(self, verification_id: str, record: Verification) -> None:
        """Store ``record`` without disturbing its place in the eviction order.

        Plain assignment to an existing key leaves the position alone, which is
        what is wanted: a verification's age is when it was submitted, not when a
        desk last reported on it, or a long examination would keep itself alive by
        making progress while a finished record ahead of it was evicted.
        """
        self._records[verification_id] = record


class InMemoryUserRepository:
    """Keeps accounts in a dict, with a second dict indexing them by address.

    Unbounded, unlike the verification store above: evicting an account would
    silently delete a registration, and the two dicts are the same size as the
    number of people who have signed up in this process's lifetime.
    """

    def __init__(self) -> None:
        self._users: dict[str, User] = {}
        #: Normalised address to user id, mirroring the unique index on the column.
        self._by_email: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def create(self, user: User) -> None:
        async with self._lock:
            # The same rejection the unique index produces in PostgreSQL, and it has
            # to be: two implementations of one Protocol must refuse the same
            # things, or a duplicate address is a 422 against the database and a
            # silent overwrite of somebody's account here.
            if user.email in self._by_email:
                raise ValidationError(
                    "That email address is already registered.",
                    details={"email": user.email},
                )
            self._users[user.id] = user
            self._by_email[user.email] = user.id

    async def get(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        user_id = self._by_email.get(normalise_email(email))
        return None if user_id is None else self._users.get(user_id)

    async def update(self, user: User) -> None:
        async with self._lock:
            existing = self._users.get(user.id)
            if existing is None:
                raise NotFoundError(
                    f"No user with id {user.id}.", details={"user_id": user.id}
                )
            if existing.email != user.email:
                if user.email in self._by_email:
                    raise ValidationError(
                        "That email address is already registered.",
                        details={"email": user.email},
                    )
                del self._by_email[existing.email]
                self._by_email[user.email] = user.id
            self._users[user.id] = user
