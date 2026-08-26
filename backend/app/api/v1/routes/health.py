"""Health route.

Included twice by the application factory: once unversioned at ``/health``, which
is what probes and orchestrators call, and once under the versioned prefix at
``/api/v1/health`` so a client that only ever speaks to ``/api/v1`` has a
liveness check inside its own namespace. Liveness is not part of the API contract
that gets versioned, which is why the unversioned mount is the canonical one.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SettingsDep
from app.schemas.health import HealthResponse
from app.utils.clock import utcnow

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
async def health(settings: SettingsDep) -> HealthResponse:
    """Report that the process is up."""
    return HealthResponse(
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT.value,
        timestamp=utcnow(),
    )
