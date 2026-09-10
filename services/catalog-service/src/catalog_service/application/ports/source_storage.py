# services/catalog-service/src/catalog_service/application/ports/source_storage.py

"""Application port persistent storage managed source content."""

from typing import Protocol
from uuid import UUID

from catalog_service.domain.section import Section
from catalog_service.domain.source import ManagedSource


class SourceStorageError(RuntimeError):
    """Infrastructure-neutral ошибка managed source storage."""


class SourceStorage(Protocol):
    """Определяет persistent content и human-readable mirror contract."""

    async def save(
        self,
        *,
        storage_key: str,
        content: bytes,
    ) -> None:
        """Атомарно сохраняет canonical source content."""

    async def read(
        self,
        *,
        storage_key: str,
    ) -> bytes:
        """Возвращает canonical content внутреннего storage object."""

    async def delete(
        self,
        *,
        storage_key: str,
    ) -> None:
        """Идемпотентно удаляет canonical storage object."""

    async def synchronize_user_tree(
        self,
        *,
        user_id: UUID,
        sections: list[Section],
        sources: list[ManagedSource],
    ) -> None:
        """Синхронизирует человекочитаемое дерево section/source на filesystem."""
