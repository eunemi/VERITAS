"""Shared API dependencies.

What belongs here is anything more than one route needs from the request: the
settings, the verification store, a service built from both. Keeping them as
``Annotated`` aliases means a route signature reads as
``async def handler(service: VerificationServiceDep)`` rather than repeating
``Depends(...)`` at every call site, and it means the dependency can be overridden
in tests through ``app.dependency_overrides``.

Every collaborator is its own ``Depends`` hop — a service depends on the repository
dependency rather than reaching for ``app.state`` itself. That costs a few lines and
buys the thing that makes these routes testable: a test can override
``get_verification_repository`` alone and the real service is still exercised, or
override ``get_verification_service`` and replace the lot. A service that fetched
its own collaborators would leave only the second option.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, StoreBackend, get_settings
from app.core.errors import AuthenticationError
from app.domain import User
from app.repositories import SqlResearchRepository
from app.repositories.base import (
    ResearchRepository,
    UserRepository,
    VerificationRepository,
)
from app.services.auth import AuthService
from app.services.claims import ClaimExtractionService
from app.services.research import WebResearchService
from app.services.verification import VerificationService

#: Process settings. Wrapped in `Depends` rather than imported directly at the
#: call site so tests can override it without touching the lru_cache.
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_verification_repository(request: Request) -> VerificationRepository:
    """Return the process-wide verification store.

    Read off ``app.state``, where :func:`app.main.create_app` put it, rather than
    held in a module-level global. One app instance owns one store, so two apps in
    one test session — which is what the fixtures build — cannot see each other's
    records.
    """
    return request.app.state.verification_repository


RepositoryDep = Annotated[
    VerificationRepository, Depends(get_verification_repository)
]


def get_verification_service(
    repository: RepositoryDep, settings: SettingsDep
) -> VerificationService:
    """Build the verification service for this request.

    A fresh instance per request, deliberately. It holds no state of its own — the
    records live in the repository — so construction is two attribute assignments,
    and a per-request instance means nothing can accumulate on it by accident.
    """
    return VerificationService(repository=repository, settings=settings)


VerificationServiceDep = Annotated[
    VerificationService, Depends(get_verification_service)
]


def get_claim_service(settings: SettingsDep) -> ClaimExtractionService:
    """Build the claim extraction service for this request."""
    return ClaimExtractionService(settings=settings)


ClaimServiceDep = Annotated[ClaimExtractionService, Depends(get_claim_service)]


def get_research_store(settings: SettingsDep) -> ResearchRepository | None:
    """The research store, or ``None`` when running without a database.

    ``None`` rather than a no-op implementation: research is a result a caller gets
    back either way, and a null store would make "nothing was written" and "it was
    written" indistinguishable from inside the service. The service treats an
    absent store as "do not persist", which is exactly what ``memory`` means.
    """
    if settings.VERIFICATION_STORE is StoreBackend.MEMORY:
        return None
    return SqlResearchRepository()


ResearchStoreDep = Annotated[
    ResearchRepository | None, Depends(get_research_store)
]


def get_research_service(
    settings: SettingsDep,
    extractor: ClaimServiceDep,
    store: ResearchStoreDep,
) -> WebResearchService:
    """Build the web research service for this request.

    The extractor arrives through its own dependency rather than being constructed
    here, so a test can substitute extraction alone and still exercise the real
    dedup, evidence and dating — which is the half of this feature worth testing
    without a network. The store arrives the same way, and is optional: a research
    request answers with what it found whether or not it could be recorded.
    """
    return WebResearchService(settings=settings, extractor=extractor, store=store)


ResearchServiceDep = Annotated[WebResearchService, Depends(get_research_service)]


# ---------------------------------------------------------------------- auth ---


def get_user_repository(request: Request) -> UserRepository:
    """Return the process-wide accounts store, put there by ``create_app``."""
    return request.app.state.user_repository


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]


def get_auth_service(
    users: UserRepositoryDep, settings: SettingsDep
) -> AuthService:
    """Build the auth service for this request."""
    return AuthService(users=users, settings=settings)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]

#: Reads `Authorization: Bearer <token>`.
#:
#: `auto_error=False` is the load-bearing argument. Left at its default, this class
#: raises FastAPI's own `HTTPException` for a missing or malformed header, which
#: renders as `{"detail": ...}` — and every non-2xx from this API is
#: `{"error": {...}}`, built by the handlers in `app.core.exception_handlers`. With
#: it off, the absence of a usable header arrives here as `None` and the decision
#: about what that means is made below, in this application's own error type.
#:
#: Not `OAuth2PasswordBearer`, for the same reason plus one: it advertises a
#: form-encoded `username`/`password` token endpoint, and `POST /auth/login` takes
#: JSON with an `email`.
bearer_scheme = HTTPBearer(
    scheme_name="Bearer",
    description="An access token from POST /auth/login.",
    auto_error=False,
)

CredentialsDep = Annotated[
    HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
]


async def get_current_user(
    credentials: CredentialsDep, service: AuthServiceDep
) -> User:
    """The signed-in account, or 401.

    For routes that require an account. The token is verified and the account
    re-read on every request — see
    :meth:`app.services.auth.AuthService.user_for_token` for why the second half
    matters.
    """
    if credentials is None:
        raise AuthenticationError("This endpoint requires a bearer token.")
    return await service.user_for_token(credentials.credentials)


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_optional_user(
    credentials: CredentialsDep, service: AuthServiceDep
) -> User | None:
    """The signed-in account, or ``None`` when the caller sent no token.

    For routes that work either way. A *missing* token is anonymous; a token that
    is present and rejected is still a 401. Treating a rejected token as anonymous
    would silently drop ownership of whatever the caller was doing — an expired
    session would go on submitting verifications that its owner could never list.
    """
    if credentials is None:
        return None
    return await service.user_for_token(credentials.credentials)


OptionalUserDep = Annotated[User | None, Depends(get_optional_user)]

