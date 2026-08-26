"""Password hashing.

Argon2id through ``argon2-cffi``, at the library's own default parameters. Those
defaults track OWASP's current guidance and are raised by the library when the
guidance moves, which is worth more than a set of constants pinned here in 2026 and
never revisited.

``argon2`` is imported inside :func:`_hasher` rather than at module scope, matching
:mod:`app.nlp.resources` and :mod:`app.vectorstore.chroma`. The reason it might be
absent is the same; the consequence is not. Those packages degrade a feature, and
this one cannot. **There is no fallback hash.** A missing library raises
:class:`~app.core.errors.ConfigurationError` naming the install, because the only
alternatives are storing the password in a weaker form or storing it as it arrived,
and both are worse than the request failing.

Nothing above this module holds a plaintext password beyond one call.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Any

from app.core.errors import ConfigurationError, ValidationError

#: Longest password accepted, in characters. Argon2 hashes its whole input rather
#: than truncating the way bcrypt does at 72 bytes, so an unbounded field is a cheap
#: way to make one request occupy a worker for a long time. 128 is far above any
#: real passphrase and far below anything worth worrying about.
MAX_PASSWORD_LENGTH = 128

#: Shortest password accepted — NIST SP 800-63B's floor. Length is the only property
#: worth enforcing; composition rules push people towards `Passw0rd!`, and the
#: guidance dropped them.
MIN_PASSWORD_LENGTH = 8


@lru_cache(maxsize=1)
def _hasher() -> Any:
    """Return the process-wide ``PasswordHasher``.

    Cached because two hashers would be two sets of parameters, and a stored hash
    is only verifiable against parameters compatible with the ones that made it.
    """
    try:
        from argon2 import PasswordHasher
    except ImportError as exc:
        raise ConfigurationError(
            "argon2-cffi is not installed, so passwords cannot be hashed. "
            "Install it with `pip install argon2-cffi`.",
            details={"package": "argon2-cffi"},
        ) from exc
    return PasswordHasher()


def hash_password(password: str) -> str:
    """Return an Argon2id hash of ``password``, salt and parameters included.

    The result is the full PHC-format encoding, so a hash written under one set of
    parameters stays verifiable after the library's defaults move.
    """
    _ensure_hashable(password)
    encoded: str = _hasher().hash(password)
    return encoded


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether ``password`` produced ``password_hash``.

    Every rejection is a plain ``False`` — a wrong password, a hash this build
    cannot read, and the empty string carried by a record written before
    registration existed. Reporting which one it was would put the difference into
    a response, and "your password is wrong" and "your account has no password" are
    not facts a caller is entitled to tell apart.
    """
    if not password_hash or len(password) > MAX_PASSWORD_LENGTH:
        return False

    hasher = _hasher()
    from argon2.exceptions import InvalidHashError, VerificationError

    try:
        return bool(hasher.verify(password_hash, password))
    except (VerificationError, InvalidHashError):
        # Both are rejections rather than bugs: VerifyMismatchError, a subclass of
        # VerificationError, is the wrong password; InvalidHashError is a stored
        # hash this build cannot parse.
        return False


def verify_decoy(password: str) -> None:
    """Verify ``password`` against a throwaway hash and discard the result.

    Called on the no-such-account path of a login so that both outcomes cost the
    same. Without it, "unknown address" returns in microseconds while "wrong
    password" pays for a full Argon2 verify — a reliable answer to "does this
    address have an account here" for anyone holding a list of addresses.
    """
    verify_password(password, _decoy_hash())


@lru_cache(maxsize=1)
def _decoy_hash() -> str:
    """A hash of a random string nobody holds, computed once per process.

    Generated rather than checked in. A constant in source is a hash whose
    plaintext is public, and while nothing compares against this one on a path that
    matters, a published hash invites exactly one wrong assumption.
    """
    return hash_password(secrets.token_urlsafe(32))


def _ensure_hashable(password: str) -> None:
    """Reject a password outside the accepted length before it reaches Argon2.

    The request schemas bound the field too. This is that invariant restated where
    it is enforced, so a caller arriving from a script or a later endpoint cannot
    store something the login route would afterwards refuse.
    """
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValidationError(
            f"A password must be between {MIN_PASSWORD_LENGTH} and "
            f"{MAX_PASSWORD_LENGTH} characters.",
            details={
                "min_length": MIN_PASSWORD_LENGTH,
                "max_length": MAX_PASSWORD_LENGTH,
            },
        )
