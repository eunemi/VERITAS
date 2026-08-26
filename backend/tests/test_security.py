"""Password hashing and token verification, one level below the endpoints.

The endpoint tests in ``test_auth_api.py`` check that the right status comes back.
These check the two things a status cannot show: that a stored hash is a hash of a
salt and a password rather than the password, and that a decoder refuses tokens it
must refuse — a forged algorithm, a missing expiry, a refresh token where an access
token belongs.

Several tests forge a token with the application's own key, which is the only way to
reach the checks that happen *after* the signature verifies.
"""

from __future__ import annotations

import base64
import json
from importlib.util import find_spec
from typing import Any

import pytest

from app.core.config import Settings
from app.core.errors import AuthenticationError, ConfigurationError, ValidationError
from app.security import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_decoy,
    verify_password,
)

#: Neither library has a degraded mode — there is no weaker hash and no unsigned
#: token — so a checkout without them cannot exercise any of this. Computed here
#: rather than through a module-scope ``pytest.importorskip``, which would put a
#: statement above the imports and make every one of them an E402.
pytestmark = pytest.mark.skipif(
    find_spec("argon2") is None or find_spec("jwt") is None,
    reason="argon2-cffi and PyJWT are needed for the authentication tests",
)

PASSWORD = "correct horse battery staple"


def secret(settings: Settings) -> str:
    """The configured signing key, for tests that forge a token with it."""
    assert settings.JWT_SECRET_KEY is not None
    return settings.JWT_SECRET_KEY.get_secret_value()


def claims_of(token: str) -> dict[str, Any]:
    """Read a token's payload without verifying it, to edit and re-sign."""
    import jwt

    payload: dict[str, Any] = jwt.decode(
        token, options={"verify_signature": False}, algorithms=["HS256"]
    )
    return payload


def resigned(payload: dict[str, Any], settings: Settings, algorithm: str) -> str:
    """Sign ``payload`` with the application's key under ``algorithm``."""
    import jwt

    token: str = jwt.encode(payload, secret(settings), algorithm=algorithm)
    return token


def unsigned(payload: dict[str, Any]) -> str:
    """Encode ``payload`` as a well-formed ``alg: none`` JWT with no signature.

    Built by hand rather than through the library, because a library asked to
    produce this may refuse to. What is under test is the decoder's response to one
    that arrives, not whether PyJWT will make one.
    """

    def segment(part: dict[str, Any]) -> str:
        raw = json.dumps(part, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{segment({'alg': 'none', 'typ': 'JWT'})}.{segment(payload)}."


# ------------------------------------------------------------------ hashing ---


async def test_a_hash_is_not_the_password() -> None:
    encoded = hash_password(PASSWORD)

    assert PASSWORD not in encoded
    assert encoded.startswith("$argon2id$")


async def test_one_password_hashes_two_ways() -> None:
    """A per-hash salt, which is what stops one leaked table becoming a lookup."""
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


async def test_the_right_password_verifies() -> None:
    assert verify_password(PASSWORD, hash_password(PASSWORD)) is True


async def test_the_wrong_password_does_not() -> None:
    assert verify_password("not the password", hash_password(PASSWORD)) is False


async def test_an_empty_stored_hash_verifies_nothing() -> None:
    """What a record written before registration existed carries.

    A hasher handed an empty string raises, and an exception here would turn a
    login attempt against such a row into a 500.
    """
    assert verify_password(PASSWORD, "") is False


async def test_an_unreadable_stored_hash_is_a_rejection_not_a_crash() -> None:
    assert verify_password(PASSWORD, "$argon2id$nonsense") is False


async def test_an_overlong_password_is_refused_before_it_is_hashed() -> None:
    """The DoS bound, restated at the point of use: no Argon2 call happens."""
    stored = hash_password(PASSWORD)

    assert verify_password("x" * (MAX_PASSWORD_LENGTH + 1), stored) is False


@pytest.mark.parametrize(
    "password",
    ["", "x" * (MIN_PASSWORD_LENGTH - 1), "x" * (MAX_PASSWORD_LENGTH + 1)],
)
async def test_a_password_outside_the_bounds_cannot_be_stored(password: str) -> None:
    with pytest.raises(ValidationError) as caught:
        hash_password(password)

    assert caught.value.details == {
        "min_length": MIN_PASSWORD_LENGTH,
        "max_length": MAX_PASSWORD_LENGTH,
    }


async def test_the_decoy_verify_discards_its_result() -> None:
    """It exists for the time it takes, so the only contract is that it returns."""
    assert verify_decoy(PASSWORD) is None


# ------------------------------------------------------------------- tokens ---


async def test_an_access_token_round_trips(settings: Settings) -> None:
    issued = create_access_token(subject="user-1", settings=settings)

    claims = decode_token(issued.token, settings=settings)

    assert claims.subject == "user-1"
    assert claims.token_type is TokenType.ACCESS
    assert claims.token_id


async def test_two_tokens_for_one_subject_have_different_ids(
    settings: Settings,
) -> None:
    """``jti`` is per token, so a revocation list has something to key on."""
    first = create_access_token(subject="user-1", settings=settings)
    second = create_access_token(subject="user-1", settings=settings)

    assert (
        decode_token(first.token, settings=settings).token_id
        != decode_token(second.token, settings=settings).token_id
    )


async def test_expires_in_counts_down_from_the_configured_lifetime(
    settings: Settings,
) -> None:
    issued = create_access_token(subject="user-1", settings=settings)

    ceiling = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert ceiling - 5 <= issued.expires_in <= ceiling


async def test_a_token_signed_with_another_key_is_refused(settings: Settings) -> None:
    """The whole point of a signature: another deployment's token is not one here."""
    other = settings.model_copy(update={"JWT_SECRET_KEY": "a-different-secret"})
    issued = create_access_token(subject="user-1", settings=other)

    with pytest.raises(AuthenticationError):
        decode_token(issued.token, settings=settings)


async def test_an_unsigned_token_is_refused(settings: Settings) -> None:
    """`alg: none`. Accepted by any decoder that reads the algorithm off the token."""
    real = create_access_token(subject="user-1", settings=settings)

    with pytest.raises(AuthenticationError):
        decode_token(unsigned(claims_of(real.token)), settings=settings)


async def test_a_token_signed_with_another_algorithm_is_refused(
    settings: Settings,
) -> None:
    """Same key, different `alg`. Only the configured one is in the accepted list."""
    real = create_access_token(subject="user-1", settings=settings)
    forged = resigned(claims_of(real.token), settings, "HS512")

    with pytest.raises(AuthenticationError):
        decode_token(forged, settings=settings)


@pytest.mark.parametrize("missing", ["exp", "iat", "jti", "type", "sub"])
async def test_a_token_missing_a_required_claim_is_refused(
    settings: Settings, missing: str
) -> None:
    """A token with no `exp` is a token that never expires."""
    real = create_access_token(subject="user-1", settings=settings)
    payload = claims_of(real.token)
    del payload[missing]

    with pytest.raises(AuthenticationError):
        decode_token(resigned(payload, settings, "HS256"), settings=settings)


async def test_an_expired_token_is_refused(settings: Settings) -> None:
    """An hour into the past, so the small decode leeway cannot cover it."""
    stale = settings.model_copy(update={"ACCESS_TOKEN_EXPIRE_MINUTES": -60})
    issued = create_access_token(subject="user-1", settings=stale)

    with pytest.raises(AuthenticationError) as caught:
        decode_token(issued.token, settings=settings)

    assert "expired" in str(caught.value)


async def test_a_refresh_token_does_not_authenticate_a_request(
    settings: Settings,
) -> None:
    """Both kinds are signed with one key, so the `type` claim is the only guard."""
    issued = create_refresh_token(subject="user-1", settings=settings)

    with pytest.raises(AuthenticationError):
        decode_token(issued.token, settings=settings)

    accepted = decode_token(
        issued.token, settings=settings, expected=TokenType.REFRESH
    )
    assert accepted.token_type is TokenType.REFRESH


async def test_garbage_is_refused_rather_than_raising_from_the_library(
    settings: Settings,
) -> None:
    with pytest.raises(AuthenticationError):
        decode_token("not.a.token", settings=settings)


async def test_an_empty_subject_is_refused(settings: Settings) -> None:
    """`require` proves `sub` is present, not that it names anybody."""
    real = create_access_token(subject="user-1", settings=settings)
    payload = claims_of(real.token)
    payload["sub"] = ""

    with pytest.raises(AuthenticationError):
        decode_token(resigned(payload, settings, "HS256"), settings=settings)


async def test_without_a_signing_key_nothing_is_issued(settings: Settings) -> None:
    """No generated-per-process fallback: a missing key is a configuration error.

    ``ENVIRONMENT=local`` is the one case the settings validator lets through,
    which is exactly the case this raise exists for.
    """
    keyless = settings.model_copy(update={"JWT_SECRET_KEY": None})

    with pytest.raises(ConfigurationError) as caught:
        create_access_token(subject="user-1", settings=keyless)

    assert caught.value.details == {"setting": "JWT_SECRET_KEY"}
