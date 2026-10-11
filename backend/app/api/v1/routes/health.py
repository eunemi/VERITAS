"""Health routes.

Included twice by the application factory: once unversioned at ``/health``, which
is what probes and orchestrators call, and once under the versioned prefix at
``/api/v1/health`` so a client that only ever speaks to ``/api/v1`` has a
liveness check inside its own namespace. Liveness is not part of the API contract
that gets versioned, which is why the unversioned mount is the canonical one.

The public uptime-monitor route is kept on its own router because it belongs at
``/api/health`` only. Including the existing router under ``/api`` would also
create an accidental ``/api/api/v1/health`` mount.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SettingsDep
from app.schemas.health import HealthResponse, PublicHealthResponse
from app.utils.clock import utcnow

router = APIRouter(tags=["health"])
public_router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
async def health(settings: SettingsDep) -> HealthResponse:
    """Report that the process is up."""
    return HealthResponse(
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT.value,
        timestamp=utcnow(),
    )


@public_router.get(
    "/api/health",
    response_model=PublicHealthResponse,
    summary="Public liveness check",
)
async def public_health() -> PublicHealthResponse:
    """Report that the process is alive without exposing deployment metadata."""
    return PublicHealthResponse(timestamp=utcnow())
