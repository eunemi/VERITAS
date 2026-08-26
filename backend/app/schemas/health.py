"""Health response shape."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Liveness answer.

    Deliberately free of dependency checks. This endpoint answers one question —
    "is this process up and serving?" — because that is what a container
    orchestrator restarts on. A check that also pings Postgres and the LLM
    provider would make an unrelated outage look like a dead process and get the
    container killed during it. Readiness, when it is needed, is a separate
    endpoint with a separate meaning.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = Field(
        default="ok", description="Always 'ok'; a failing process cannot answer."
    )
    service: str = Field(description="Application name.")
    version: str = Field(description="Application version.")
    environment: str = Field(description="Deployment environment.")
    timestamp: datetime = Field(description="Server time, UTC, when answered.")
