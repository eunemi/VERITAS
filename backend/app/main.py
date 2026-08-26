"""Application factory and ASGI entry point.

``create_app`` builds and returns the application; ``app`` at the bottom is the
instance uvicorn imports. Keeping construction in a function is what lets a test
build a fresh application with different settings instead of importing a
module-level singleton that was configured at import time.

Nothing here contains business logic. This module wires five things together —
logging, the stores, middleware, exception handlers, routers — and owns the startup
and shutdown sequence.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.api.v1.routes import health as health_route
from app.core.config import Settings, StoreBackend, get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from app.database.session import dispose_engine
from app.repositories import (
    InMemoryUserRepository,
    InMemoryVerificationRepository,
    SqlUserRepository,
    SqlVerificationRepository,
    UserRepository,
    VerificationRepository,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown.

    Nothing is eagerly connected on startup. The database engine builds its pool
    on first query, and every external provider is constructed when first
    resolved, so the process becomes able to answer ``/health`` immediately rather
    than after a dependency handshake that may fail for reasons unrelated to this
    service being alive.
    """
    settings: Settings = app.state.settings
    logger.info(
        "application starting",
        extra={
            "environment": settings.ENVIRONMENT.value,
            "version": settings.APP_VERSION,
        },
    )

    yield

    await dispose_engine()
    logger.info("application stopped")


def build_verification_store(settings: Settings) -> VerificationRepository:
    """Resolve the configured store.

    The only place in the application that names a concrete repository. The return
    annotation is the Protocol, so a caller — including ``create_app`` — cannot
    reach past it to something only one implementation has.

    The SQL store is constructed without a session factory, so it resolves one on
    first use. That matters here specifically: ``app = create_app()`` runs at import
    of this module, and building the engine eagerly would open a pool during import
    of anything that touches :mod:`app.main`, including a test collecting it.
    """
    if settings.VERIFICATION_STORE is StoreBackend.MEMORY:
        return InMemoryVerificationRepository()
    return SqlVerificationRepository()


def build_user_store(settings: Settings) -> UserRepository:
    """Resolve the configured accounts store.

    Follows ``VERIFICATION_STORE`` rather than having a setting of its own, so one
    switch decides whether this process needs PostgreSQL at all. Under ``memory``
    that means accounts do not survive a restart — which is the whole meaning of
    that value, and why it is not the default.
    """
    if settings.VERIFICATION_STORE is StoreBackend.MEMORY:
        return InMemoryUserRepository()
    return SqlUserRepository()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Passing ``settings`` explicitly is the seam for tests; in the running process
    it is omitted and the cached environment-derived settings are used.
    """
    settings = settings or get_settings()

    configure_logging(level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        summary="Evidence-based verification of news, claims, and media artifacts.",
        lifespan=lifespan,
        # Interactive docs are closed in production. The OpenAPI document itself
        # goes with them: it is a map of the surface and there is no reason to
        # publish one.
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    # Read by the lifespan handler and available to any route that needs the
    # application's own configuration rather than the request-scoped dependency.
    app.state.settings = settings

    # One store per application, built here rather than at module scope so that two
    # applications in one test session cannot see each other's records. Reached
    # through the dependencies in `app.api.deps`, which is what makes them
    # overridable; nothing imports either directly.
    app.state.verification_repository = build_verification_store(settings)
    app.state.user_repository = build_user_store(settings)

    # Order matters and is why both are registered here. Starlette runs
    # middleware in reverse registration order, so CORS — added last — is the
    # outermost layer and gets to answer a preflight before anything else runs,
    # while the request-id layer still wraps every real handler.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # A browser can only read a response header that is named here. The CORS
        # safelist is seven headers long and includes none of these three: the
        # correlation id the frontend logs, the `Location` pointing at a submitted
        # verification, and the `Retry-After` telling a poller when to come back.
        # Omitting any of them makes the browser client read `null` while curl,
        # which is not bound by the safelist, sees the header perfectly — so the
        # gap only shows up in the one place that matters.
        expose_headers=[REQUEST_ID_HEADER, "Location", "Retry-After"],
    )

    register_exception_handlers(app)

    # Unversioned liveness, for probes and orchestrators.
    app.include_router(health_route.router)
    # The versioned surface.
    app.include_router(v1_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
