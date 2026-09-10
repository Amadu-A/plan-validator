# services/retrieval-service/src/retrieval_service/application/ports/source_index_repository.py

"""Application repository port Retrieval source-index registry."""

from typing import Protocol
from uuid import UUID

from retrieval_service.domain.source_index import ManagedSourceIndex, SourceKind


class SourceIndexRepository(Protocol):
    """Хранит active fingerprints и Catalog-owned source metadata."""

    async def add(self, source: ManagedSourceIndex) -> None:
        """Добавляет новый source registry row."""

    async def get(self, source_id: UUID) -> ManagedSourceIndex | None:
        """Возвращает source registry row без блокировки."""

    async def get_for_update(self, source_id: UUID) -> ManagedSourceIndex | None:
        """Блокирует source registry row для lifecycle switch."""

    async def save(self, source: ManagedSourceIndex) -> None:
        """Сохраняет полное актуальное состояние source registry row."""

    async def list_active_version_keys(
        self,
        *,
        user_id: UUID,
        kind: SourceKind,
        section_ids: tuple[UUID, ...],
        source_ids: tuple[UUID, ...],
    ) -> tuple[str, ...]:
        """Возвращает search-visible version keys после exact metadata filters."""
