# services/catalog-service/src/catalog_service/application/ports/source_repository.py

"""Application port persistence managed N/U sources."""

from typing import Protocol
from uuid import UUID

from catalog_service.domain.source import ManagedSource, SourceKind


class ManagedSourceRepository(Protocol):
    """Определяет persistence operations managed source aggregate."""

    async def list_for_user_section(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
        kind: SourceKind,
    ) -> list[ManagedSource]:
        """Возвращает не удалённые sources одной section и kind."""

    async def list_active_for_user(
        self,
        *,
        user_id: UUID,
    ) -> list[ManagedSource]:
        """Возвращает active sources для materialized filesystem tree."""

    async def get_for_user_kind(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: SourceKind,
    ) -> ManagedSource | None:
        """Возвращает source только внутри ownership/kind scope."""

    async def get_for_user_kind_for_update(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: SourceKind,
    ) -> ManagedSource | None:
        """Возвращает source с row lock для lifecycle transition."""

    async def add(self, source: ManagedSource) -> None:
        """Добавляет source metadata в текущую transaction."""

    async def update(self, source: ManagedSource) -> None:
        """Сохраняет lifecycle state source."""

    async def has_live_in_subtree(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> bool:
        """Проверяет наличие не удалённых sources в section subtree."""

    async def purge_deleted_in_subtree(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> None:
        """Удаляет только already-deleted metadata перед удалением section."""
