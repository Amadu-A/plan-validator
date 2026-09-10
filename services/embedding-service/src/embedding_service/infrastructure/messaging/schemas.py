# services/embedding-service/src/embedding_service/infrastructure/messaging/schemas.py

"""Pydantic message schemas RabbitMQ embedding RPC."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EmbeddingJobRequest(BaseModel):
    """Версионированный request одной expensive embedding операции."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    job_id: UUID
    correlation_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1)
    instruction: str | None = Field(default=None, max_length=2000)


class EmbeddingBatchJobRequest(BaseModel):
    """Версионированный batch request с одной загрузкой Qwen checkpoint."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    job_id: UUID
    correlation_id: str = Field(min_length=1, max_length=128)
    texts: list[str] = Field(min_length=1, max_length=1024)
    instruction: str | None = Field(default=None, max_length=2000)


class EmbeddingTelemetryMessage(BaseModel):
    """Безопасная telemetry, возвращаемая benchmark/caller."""

    available_ram_bytes: int
    free_vram_before_bytes: int
    total_vram_bytes: int
    model_load_ms: float
    encode_ms: float
    total_ms: float
    peak_allocated_vram_bytes: int


class EmbeddingJobSuccess(BaseModel):
    """Успешный RPC response normalized embedding."""

    schema_version: Literal[1] = 1
    status: Literal["success"] = "success"
    job_id: UUID
    model: str
    dimension: int
    vector: list[float]
    telemetry: EmbeddingTelemetryMessage


class EmbeddingBatchJobSuccess(BaseModel):
    """Успешный RPC response normalized embedding batch."""

    schema_version: Literal[1] = 1
    status: Literal["success"] = "success"
    job_id: UUID
    model: str
    dimension: int
    vector_encoding: Literal["float32-le-base64"] = "float32-le-base64"
    vector_count: int = Field(ge=1)
    vectors_b64: str = Field(min_length=1)
    telemetry: EmbeddingTelemetryMessage


class EmbeddingJobFailure(BaseModel):
    """Безопасный RPC response ошибки без traceback/secrets."""

    schema_version: Literal[1] = 1
    status: Literal["error"] = "error"
    job_id: UUID | None = None
    error_type: str
    message: str
