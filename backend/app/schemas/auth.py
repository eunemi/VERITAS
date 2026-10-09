"""Request and response shapes for authentication.

Two things worth stating about what is *not* here.

**No ``password`` field on any response model, and no ``password_hash`` anywhere.**
:class:`UserOut` names the four fields it publishes rather than deriving them from
:class:`app.domain.User`, so adding a field to the domain type cannot leak it — the
hash in particular, which sits on that dataclass and must never reach the wire.

**No ``EmailStr``.** Address validation is :func:`app.domain.normalise_email`'s job
and happens once, in the domain, on the value the store will key on. A second
validator at the edge would mean two definitions of a valid address and a way for
them to disagree; it would also add ``email-validator`` as a dependency to restate a
rule this application already has.

Field names are snake_case, and there is no ``alias_generator`` here or anywhere else
in this package — see the note in :mod:`app.schemas`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field

from app.domain import User
from app.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH

#: Longest address RFC 5321 allows, matching the column in :mod:`app.models.user`.
MAX_EMAIL_LENGTH = 320


# ============================================================== requests ====


class RegisterRequest(BaseModel):
    """Open an account."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(
        max_length=MAX_EMAIL_LENGTH,
        description="Case-insensitive. Stored lower-cased and trimmed.",
        examples=["reader@example.com"],
    )
    password: str = Field(
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH,
        description=(
            f"Between {MIN_PASSWORD_LENGTH} and {MAX_PASSWORD_LENGTH} characters. "
            "Length is the only rule; there are no composition requirements."
        ),
    )
    display_name: str = Field(
        default="",
        max_length=120,
        description="Printed on the record. Defaults to the local part of the email.",
    )


class LoginRequest(BaseModel):
    """Exchange an email and password for an access token."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=MAX_EMAIL_LENGTH)
    # Bounded, but with no minimum: a floor here would reject a password shorter
    # than today's rule and, in doing so, tell the caller their password predates it.
    # The maximum is not cosmetic — Argon2 hashes its whole input, so an unbounded
    # field lets one request hold a worker for as long as it likes.
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


# ============================================================= responses ====


class UserOut(BaseModel):
    """An account, as the API publishes it.

    Four fields and no more. ``password_hash`` is on the domain object and is
    deliberately absent here; see the module docstring.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    email: str
    display_name: str
    created_at: datetime

    @classmethod
    def from_domain(cls, user: User) -> Self:
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            created_at=user.created_at,
        )


class TokenOut(BaseModel):
    """Body of a successful ``POST /auth/login``.

    ``token_type`` is a constant, and it is published anyway: a client reading
    ``Authorization: {token_type} {access_token}`` out of this body needs no
    knowledge of the scheme, and the field is what a later second scheme would
    change rather than break.

    There is no refresh token. Only an access token is issued and there is no
    endpoint that would exchange one — see the auth note in ``backend/README.md``.
    """

    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: Literal["bearer"] = Field(default="bearer")
    expires_in: int = Field(
        description="Seconds until the token stops being accepted.",
    )
    user: UserOut = Field(
        description="The signed-in account, so a client need not call /auth/me.",
    )
