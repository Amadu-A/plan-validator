# services/document-service/src/document_service/application/ports/repositories.py

"""Persistence repository ports Document Service."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from document_service.domain.models import ProjectDocument


class ProjectDocumentRepository(Protocol):
    """Хранит owner-scoped Project Document metadata."""

    async def add(self, document: ProjectDocument) -> None:
        """Добавляет document."""

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
    ) -> ProjectDocument | None:
        """Возвращает document внутри ownership scope."""

    async def get_for_user_for_update(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
    ) -> ProjectDocument | None:
        """Возвращает document с row lock."""

    async def list_for_user(self, user_id: UUID) -> list[ProjectDocument]:
        """Возвращает visible documents пользователя."""

    async def list_cleanup_candidates(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> list[ProjectDocument]:
        """Возвращает expired/delete-pending documents."""

    async def save(self, document: ProjectDocument) -> None:
        """Сохраняет immutable-domain state."""
