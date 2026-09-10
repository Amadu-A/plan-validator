# services/catalog-service/src/catalog_service/application/ports/source_storage.py

"""Application port persistent storage managed source content."""

from typing import Protocol


class SourceStorageError(RuntimeError):
    """Infrastructure-neutral ошибка managed source storage."""


class SourceStorage(Protocol):
    """Определяет минимальный content storage contract Stage 7."""

    async def save(self, *, storage_key: str, content: bytes) -> None:
        """Атомарно сохраняет content по внутреннему storage key."""

    async def read(self, *, storage_key: str) -> bytes:
        """Возвращает content внутреннего storage object."""

    async def delete(self, *, storage_key: str) -> None:
        """Идемпотентно удаляет storage object."""
