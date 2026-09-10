# services/catalog-service/src/catalog_service/application/ports/section_repository.py

"""Application port persistence пользовательских sections."""

from typing import Protocol
from uuid import UUID

from catalog_service.domain.section import Section


class SectionRepository(Protocol):
    """Определяет persistence operations section aggregate."""

    async def list_for_user(self, user_id: UUID) -> list[Section]:
        """Возвращает все sections пользователя в стабильном порядке."""

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> Section | None:
        """Возвращает section только внутри ownership scope пользователя."""

    async def add(self, section: Section) -> None:
        """Добавляет новый section в текущую transaction."""

    async def update(self, section: Section) -> None:
        """Сохраняет обновлённое состояние section."""

    async def delete(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> None:
        """Удаляет section пользователя и database-cascade descendants."""
