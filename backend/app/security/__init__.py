"""Password hashing and token signing.

Two modules, both of which the rest of the application reaches only through the
:class:`app.services.auth.AuthService`. Nothing here knows what a request is, and
nothing here touches a store — which is what lets both be tested with no database
and no application.

Both defer their library import to first use, and neither has a fallback. See the
note in :mod:`app.security.passwords`: a missing ``argon2-cffi`` or ``PyJWT`` is a
:class:`~app.core.errors.ConfigurationError`, never a weaker hash or an unsigned
token.
"""

from __future__ import annotations

from app.security.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    hash_password,
    verify_decoy,
    verify_password,
)
from app.security.tokens import (
    IssuedToken,
    TokenClaims,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
)

__all__ = [
    "MAX_PASSWORD_LENGTH",
    "MIN_PASSWORD_LENGTH",
    "IssuedToken",
    "TokenClaims",
    "TokenType",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_password",
    "verify_decoy",
    "verify_password",
]
