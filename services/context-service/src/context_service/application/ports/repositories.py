# services/context-service/src/context_service/application/ports/repositories.py

"""Persistence repository ports Context Service."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from context_service.domain.models import (
    ContextIndexJob,
    ContextSource,
    ContextSourceKind,
    ProjectContext,
)


class ProjectContextRepository(Protocol):
    """Хранит owner-scoped temporary Project Context."""

    async def add(self, context: ProjectContext) -> None:
        """Добавляет новый context."""

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
    ) -> ProjectContext | None:
        """Возвращает context только внутри ownership scope."""

    async def get_for_user_for_update(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
    ) -> ProjectContext | None:
        """Блокирует context row для lifecycle transition."""

    async def save(self, context: ProjectContext) -> None:
        """Сохраняет актуальное immutable-domain состояние."""


class ContextSourceRepository(Protocol):
    """Хранит T/PZ metadata временного context."""

    async def add(self, source: ContextSource) -> None:
        """Добавляет source."""

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
    ) -> ContextSource | None:
        """Возвращает source внутри ownership scope."""

    async def get_for_user_for_update(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
    ) -> ContextSource | None:
        """Блокирует source row."""

    async def get_for_context_kind(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
        kind: ContextSourceKind,
    ) -> ContextSource | None:
        """Возвращает единственный source данного semantic kind."""

    async def save(self, source: ContextSource) -> None:
        """Сохраняет source lifecycle."""


class ContextIndexJobRepository(Protocol):
    """Хранит durable state expensive Context indexing jobs."""

    async def add(self, job: ContextIndexJob) -> None:
        """Добавляет persistent job."""

    async def get(self, job_id: UUID) -> ContextIndexJob | None:
        """Возвращает job без row lock."""

    async def get_for_update(
        self,
        job_id: UUID,
    ) -> ContextIndexJob | None:
        """Блокирует job для state transition."""

    async def find_open_for_source_fingerprint(
        self,
        *,
        source_id: UUID,
        fingerprint: str,
    ) -> ContextIndexJob | None:
        """Ищет уже существующий non-terminal identical indexing job."""

    async def list_recoverable(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> list[ContextIndexJob]:
        """Возвращает lost publish, due retry, stale-running и expired jobs."""

    async def has_open_for_context(self, *, context_id: UUID) -> bool:
        """Проверяет, остались ли non-terminal jobs перед physical cleanup."""

    async def save(self, job: ContextIndexJob) -> None:
        """Сохраняет persistent job state."""
