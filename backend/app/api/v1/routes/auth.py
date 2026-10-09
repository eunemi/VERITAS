"""Authentication routes: open an account, sign in, read the current one.

Three endpoints, no decisions. Each converts a validated request into an
:class:`app.services.auth.AuthService` call and a domain object into a response; the
password comparison, the token signing, and every judgement about what a caller is
allowed to learn from a failure live in that service.

``POST /auth/login`` is the only endpoint here that issues a token, and it is the
first one to put behind a rate limit — see the auth note in ``backend/README.md``.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import AuthServiceDep, CurrentUserDep
from app.api.responses import COMMON_ERRORS, error
from app.schemas.auth import LoginRequest, RegisterRequest, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"], responses=COMMON_ERRORS)


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserOut,
    summary="Open an account",
    responses={
        422: error(
            "The address is not an address, the password is outside the accepted "
            "length, or the address is already registered."
        ),
    },
)
async def register(payload: RegisterRequest, service: AuthServiceDep) -> UserOut:
    """Create an account and return it.

    No token comes back. Registration creates and ``POST /auth/login``
    authenticates, so exactly one endpoint mints tokens; the client pays one extra
    round trip for that.

    A duplicate address is reported as such, which is the one place this API will
    confirm that an account exists. There is no way around it — an endpoint that
    accepted a second registration for one address would either lock the first
    account's owner out or silently sign the caller in as them.
    """
    user = await service.register(
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
    )
    return UserOut.from_domain(user)


@router.post(
    "/login",
    response_model=TokenOut,
    summary="Sign in",
    responses={401: error("Email or password is incorrect.")},
)
async def login(payload: LoginRequest, service: AuthServiceDep) -> TokenOut:
    """Exchange an email and password for a bearer token.

    Every rejection is the same 401 with the same message, whether the address is
    unknown, the password is wrong, or the account has been closed.
    """
    user, issued = await service.login(email=payload.email, password=payload.password)
    return TokenOut(
        access_token=issued.token,
        expires_in=issued.expires_in,
        user=UserOut.from_domain(user),
    )


@router.get(
    "/me",
    response_model=UserOut,
    summary="Read the signed-in account",
    responses={401: error("Missing, invalid, or expired bearer token.")},
)
async def read_current_user(user: CurrentUserDep) -> UserOut:
    """Return the account the bearer token identifies.

    The dependency has already verified the token and re-read the account, so a
    200 here means the session was live at the moment of this request rather than
    at the moment the token was signed.
    """
    return UserOut.from_domain(user)
