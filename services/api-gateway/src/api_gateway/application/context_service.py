# services/api-gateway/src/api_gateway/application/context_service.py

"""Application port временного Project Context для API Gateway."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class ContextSourceKind(StrEnum):
    """Допустимые semantic types временного Project Context."""

    TECHNICAL_ASSIGNMENT = "T"
    PROJECT_NOTE = "PZ"


class ProjectContextState(StrEnum):
    """Публично безопасный lifecycle Project Context."""

    ACTIVE = "active"
    CLEANUP_PENDING = "cleanup_pending"
    CLEANED = "cleaned"


class ContextSourceState(StrEnum):
    """Публично безопасный lifecycle временного T/PZ source."""

    AWAITING_CHUNKS = "awaiting_chunks"
    INDEXED = "indexed"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class GatewayProjectContext:
    """Transport-neutral Gateway representation временного context."""

    id: UUID
    user_id: UUID
    state: ProjectContextState
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class GatewayContextSource:
    """Transport-neutral Gateway representation T/PZ metadata."""

    id: UUID
    context_id: UUID
    user_id: UUID
    kind: ContextSourceKind
    original_name: str
    source_sha256: str
    state: ContextSourceState
    active_fingerprint: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class ContextServiceClient(Protocol):
    """Gateway port trusted internal Context Service."""

    async def create_context(
        self,
        *,
        user_id: UUID,
    ) -> GatewayProjectContext:
        """Создаёт temporary context текущего authenticated user."""

    async def get_context(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
    ) -> GatewayProjectContext:
        """Возвращает owner-scoped Project Context."""

    async def request_cleanup(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
    ) -> GatewayProjectContext:
        """Запускает logical-first cleanup Project Context."""

    async def register_source(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
        kind: ContextSourceKind,
        original_name: str,
        source_sha256: str,
    ) -> GatewayContextSource:
        """Регистрирует metadata единственного T либо PZ source."""

    async def aclose(self) -> None:
        """Закрывает owned HTTP resources."""
