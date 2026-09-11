# services/context-service/src/context_service/infrastructure/messaging/schemas.py

"""RabbitMQ message schemas recoverable Context indexing."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContextIndexJobMessage(BaseModel):
    """Минимальный durable command: payload хранится только в PostgreSQL."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1, le=1)
    job_id: UUID
    correlation_id: str = Field(min_length=1, max_length=128)
