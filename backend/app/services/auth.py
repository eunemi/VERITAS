"""Registering, signing in, and turning a token back into an account.

The one place a password is compared and the one place a token is minted. Both are
here rather than in a route so that a script, a CLI or a second transport gets the
same rules, and rather than in the store so that nothing which merely holds accounts
can also be asked to authenticate one.

Three decisions in this module are about what a caller is allowed to learn, and each
is commented where it is made:

* Login has exactly one failure — same code, same message, same cost — whether the
  address is unknown, the password is wrong, or the account is closed.
* Registration reports a taken address, because it has to; that is the one place
  this API will confirm an account exists, and it is why registration is the
  endpoint to rate-limit first.
* A token is a claim about *who*, never about *whether*. The account is re-read from
  the store on every authenticated request.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.errors import AuthenticationError, ValidationError
from app.core.logging import get_logger
from app.domain import User, normalise_email
from app.repositories.base import UserRepository
from app.security import (
    IssuedToken,
    create_access_token,
    decode_token,
    hash_password,
    verify_decoy,
    verify_password,
)

logger = get_logger(__name__)

#: The only thing a failed sign-in says. One message for an unknown address, a wrong
#: password and a deactivated account, because three messages are three answers to
#: "does this address have an account here" — the question an attacker holding a list
#: of addresses is actually asking.
CREDENTIALS_REJECTED = "Email or password is incorrect."


class AuthService:
    """Accounts, passwords and access tokens."""

    def __init__(self, *, users: UserRepository, settings: Settings) -> None:
        self._users = users
        self._settings = settings

    # ------------------------------------------------------------- register ---

    async def register(
        self, *, email: str, password: str, display_name: str = ""
    ) -> User:
        """Open an account and return it.

        Raises :class:`~app.core.errors.ValidationError` for a malformed address, a
        password outside the accepted length, or an address already registered.

        No token is issued. Registration creates; :meth:`login` authenticates. One
        endpoint minting tokens is one endpoint to rate-limit, audit and revoke
        against, and the client pays a single extra round trip for it.
        """
        user = User.registered(
            email=email,
            display_name=display_name,
            password_hash=hash_password(password),
        )
        await self._users.create(user)
        # The address is not logged. It is the identifier a person did not choose to
        # publish, and a log line is the easiest place in a system to read one out of.
        logger.info("account registered", extra={"user_id": user.id})
        return user

    # ---------------------------------------------------------------- login ---

    async def login(self, *, email: str, password: str) -> tuple[User, IssuedToken]:
        """Verify a password and return the account with a signed access token."""
        user = await self._lookup(email)

        if user is None:
            # Verify against a decoy so that an unknown address costs what a known
            # one costs. Returning here without hashing would make response time
            # the oracle that the identical message exists to close.
            verify_decoy(password)
            logger.info("sign-in rejected", extra={"reason": "no_such_account"})
            raise AuthenticationError(CREDENTIALS_REJECTED)

        # `verify_password` first and `and` second, so the hash is always computed:
        # short-circuiting on `is_active` would make a closed account answer faster
        # than an open one, which is the same leak by a different route.
        password_ok = verify_password(password, user.password_hash)
        if not (password_ok and user.is_active):
            logger.info(
                "sign-in rejected",
                extra={
                    "user_id": user.id,
                    "reason": "bad_password" if not password_ok else "inactive",
                },
            )
            raise AuthenticationError(CREDENTIALS_REJECTED)

        logger.info("sign-in accepted", extra={"user_id": user.id})
        return user, create_access_token(subject=user.id, settings=self._settings)

    # -------------------------------------------------------------- current ---

    async def user_for_token(self, token: str) -> User:
        """Return the account a bearer token identifies.

        Raises :class:`~app.core.errors.AuthenticationError` for a token that does
        not verify, has expired, is of the wrong type, or names an account that is
        gone or closed.
        """
        claims = decode_token(token, settings=self._settings)
        user = await self._users.get(claims.subject)
        # Re-read, every request. A token is valid until it expires, so trusting its
        # claims alone would let an account deactivated a minute ago keep
        # authenticating for the rest of the access-token lifetime — and deleted for
        # even longer.
        if user is None or not user.is_active:
            raise AuthenticationError("This session is no longer valid.")
        return user

    # -------------------------------------------------------------- private ---

    async def _lookup(self, email: str) -> User | None:
        """Find an account by address, treating a malformed one as absent.

        ``normalise_email`` raises for something that is not an address, which would
        make a login answer 422 where every other rejection answers 401 — a
        distinction a client can use to tell a rejected format from a rejected
        credential. Login has one failure shape, so this collapses into it.
        """
        try:
            address = normalise_email(email)
        except ValidationError:
            return None
        return await self._users.get_by_email(address)
