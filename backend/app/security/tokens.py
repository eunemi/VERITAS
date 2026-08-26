"""Issuing and verifying JWTs.

One function signs, one function verifies, and the verifying one is where the
security of the scheme actually lives. Three things it does are the reason this is a
module rather than two calls inline:

**The accepted algorithm is named, never read from the token.** ``algorithms`` is
always the single configured value. A decoder that trusts the token's own ``alg``
header accepts ``none`` and accepts an HMAC signed with the public key it thought
was RSA-only — the two classic JWT forgeries, both of which are a caller's choice
rather than a library bug. PyJWT requires the list; this passes exactly one entry.

**The claims a token must carry are required, not merely read.** A token missing
``exp`` is a token that never expires, and ``options={"require": [...]}`` is what
makes its absence a rejection instead of a ``None``.

**``type`` is checked against what the caller expected.** Access and refresh tokens
are signed with the same key, so without this claim a refresh token — long-lived by
design — authenticates a request as well as an access token does.

``jwt`` is imported inside :func:`_jwt` for the reason given in
:mod:`app.security.passwords`: the application must import without it, and its
absence must be a loud :class:`~app.core.errors.ConfigurationError` rather than a
token that goes out unsigned.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from functools import lru_cache
from typing import Any

from app.core.config import Settings
from app.core.errors import AuthenticationError, ConfigurationError
from app.utils.clock import utcnow
from app.utils.ids import new_id


class TokenType(StrEnum):
    """What a token is for.

    Carried in the ``type`` claim and checked on every decode. See the module note:
    both kinds are signed with one key, so the claim is the only thing separating
    them.
    """

    ACCESS = "access"
    REFRESH = "refresh"


#: Claims every token this application issues must carry to be accepted.
REQUIRED_CLAIMS = ["sub", "type", "exp", "iat", "jti"]

#: Seconds of clock skew tolerated between whatever signed a token and whatever is
#: verifying it. Small on purpose: it widens the window in which an expired token is
#: still accepted, and every process here reads the same clock.
LEEWAY_SECONDS = 10


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """A verified token's contents, in domain terms."""

    subject: str
    token_type: TokenType
    issued_at: datetime
    expires_at: datetime
    token_id: str


@dataclass(frozen=True, slots=True)
class IssuedToken:
    """A freshly signed token and when it stops being one."""

    token: str
    expires_at: datetime

    @property
    def expires_in(self) -> int:
        """Whole seconds of life left, for a client keeping a countdown."""
        return max(0, int((self.expires_at - utcnow()).total_seconds()))


def create_access_token(*, subject: str, settings: Settings) -> IssuedToken:
    """Sign an access token for ``subject``, which is a user id."""
    return _issue(
        subject=subject,
        token_type=TokenType.ACCESS,
        lifetime=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        settings=settings,
    )


def create_refresh_token(*, subject: str, settings: Settings) -> IssuedToken:
    """Sign a refresh token for ``subject``.

    Nothing calls this yet — there is no refresh endpoint, and ``login`` returns an
    access token only. It exists because :class:`TokenType` has two members and a
    ``type`` check is worth nothing if only one kind of token is ever minted; see
    the auth note in ``backend/README.md``.
    """
    return _issue(
        subject=subject,
        token_type=TokenType.REFRESH,
        lifetime=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        settings=settings,
    )


def decode_token(
    token: str,
    *,
    settings: Settings,
    expected: TokenType = TokenType.ACCESS,
) -> TokenClaims:
    """Verify ``token`` and return its claims.

    Raises :class:`~app.core.errors.AuthenticationError` for anything that is not a
    currently-valid token of type ``expected``: a bad signature, an expiry in the
    past, a missing required claim, a subject that is not a string, or a refresh
    token offered where an access token was wanted.
    """
    jwt = _jwt()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            _signing_key(settings),
            # The configured algorithm, not the token's. See the module docstring.
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": REQUIRED_CLAIMS},
            leeway=LEEWAY_SECONDS,
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError(
            "This session has expired. Sign in again."
        ) from exc
    except jwt.InvalidTokenError as exc:
        # The base class of every PyJWT rejection, so one branch covers a forged
        # signature, a malformed token and a missing required claim alike. The
        # message says nothing about which: a caller probing a token learns only
        # that it was refused.
        raise AuthenticationError("That token is not valid.") from exc

    subject = payload["sub"]
    if not isinstance(subject, str) or not subject:
        raise AuthenticationError("That token is not valid.")

    if payload["type"] != expected.value:
        # Both kinds are signed with the same key, so this claim is the only thing
        # stopping a long-lived refresh token from authenticating a request.
        raise AuthenticationError("That token is not valid for this request.")

    return TokenClaims(
        subject=subject,
        token_type=TokenType(payload["type"]),
        issued_at=_moment(payload["iat"]),
        expires_at=_moment(payload["exp"]),
        token_id=str(payload["jti"]),
    )


# ------------------------------------------------------------------ private ---


def _issue(
    *,
    subject: str,
    token_type: TokenType,
    lifetime: timedelta,
    settings: Settings,
) -> IssuedToken:
    issued_at = utcnow()
    expires_at = issued_at + lifetime
    payload = {
        "sub": subject,
        "type": token_type.value,
        "iat": issued_at,
        "exp": expires_at,
        # A unique id per token. Nothing revokes one yet, but a revocation list
        # keyed on anything else would have to key on the whole token string.
        "jti": new_id(),
    }
    token: str = _jwt().encode(
        payload, _signing_key(settings), algorithm=settings.JWT_ALGORITHM
    )
    return IssuedToken(token=token, expires_at=expires_at)


def _signing_key(settings: Settings) -> str:
    """Return the signing secret, refusing to invent one.

    :class:`~app.core.config.Settings` already refuses to build without a key
    outside local development, so reaching the raise here means local development
    with none set. There is deliberately no generated-per-process fallback: it would
    make every restart silently invalidate every session, and a checked-in default
    would let any copy of this repository forge a token for any deployment of it.
    """
    key = settings.JWT_SECRET_KEY
    if key is None or not key.get_secret_value():
        raise ConfigurationError(
            "JWT_SECRET_KEY is not set, so tokens cannot be signed or verified.",
            details={"setting": "JWT_SECRET_KEY"},
        )
    return key.get_secret_value()


def _moment(value: Any) -> datetime:
    """Read a NumericDate claim as an aware UTC datetime."""
    return datetime.fromtimestamp(float(value), tz=UTC)


@lru_cache(maxsize=1)
def _jwt() -> Any:
    """Return the ``jwt`` module, or raise naming the install."""
    try:
        import jwt
    except ImportError as exc:
        raise ConfigurationError(
            "PyJWT is not installed, so tokens cannot be issued or verified. "
            "Install it with `pip install PyJWT`.",
            details={"package": "PyJWT"},
        ) from exc
    return jwt
