"""Who submitted a verification.

The one aggregate here with no examination in it. A verification belongs to
somebody, and a store that cannot answer "whose is this" cannot answer "show me
mine" either — which is the whole reason the record needs an owner column.

``password_hash`` is opaque to this package. Nothing here hashes, compares or
inspects it — :mod:`app.security.passwords` is the only module that does, and
:class:`app.services.auth.AuthService` is the only caller of that. It is named for
what the column must hold, so a caller writing a plaintext password into a field
called ``password_hash`` is doing so against a stated contract rather than a vague
one.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from app.core.errors import ValidationError
from app.utils.clock import utcnow
from app.utils.ids import new_id


def normalise_email(value: str) -> str:
    """Trim and lower-case ``value``, rejecting anything that is not an address.

    Case folding happens here rather than in the store because uniqueness is
    enforced on the column: two rows differing only in case would be two accounts
    for one address, and whoever registered the second would have no way to work
    out why their password did not open the first.

    The check is deliberately shallow — a local part, an ``@``, and a dot in the
    domain. Anything stricter rejects addresses that deliver, and the only proof
    that an address is real is a message arriving at it.
    """
    email = value.strip().lower()
    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain:
        raise ValidationError(
            "That is not an email address.", details={"email": value}
        )
    return email


@dataclass(frozen=True, slots=True)
class User:
    """An account that submits verifications."""

    id: str
    email: str
    display_name: str = ""
    password_hash: str = ""
    is_active: bool = True
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    @classmethod
    def registered(
        cls,
        *,
        email: str,
        display_name: str = "",
        password_hash: str = "",
    ) -> User:
        """Open an account: fresh id, normalised address, a name to print.

        Normalisation and validation live here and not in ``__post_init__`` on
        purpose. Every row the store reads back is turned into one of these, so a
        validator in the constructor would make a row written before a rule
        existed unreadable rather than merely non-conforming — and the account
        would disappear instead of being fixable.
        """
        address = normalise_email(email)
        return cls(
            id=new_id(),
            email=address,
            display_name=display_name.strip() or address.partition("@")[0],
            password_hash=password_hash,
        )

    def deactivated(self) -> User:
        """Close the account without deleting what it submitted.

        The verifications stay: they are the record of what was examined, and the
        foreign key nulls the owner rather than cascading, so closing an account
        does not erase the examinations it paid for.
        """
        return replace(self, is_active=False, updated_at=utcnow())
