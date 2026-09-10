# services/embedding-service/src/embedding_service/transport/schemas.py

"""HTTP response schemas Embedding Service."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Operational health response."""

    model_config = ConfigDict(frozen=True)

    status: Literal["alive", "ready", "not_ready"]
    service: str
    version: str


class RuntimeStatusResponse(BaseModel):
    """Safe internal embedding runtime contract."""

    model_config = ConfigDict(frozen=True)

    model: str
    dimension: int
    queue: str
    cache_ready: bool
    gpu_required: bool
    offline_only: bool
