# services/document-service/src/document_service/application/ports/storage.py

"""Physical file storage port Document Service."""

from typing import Protocol


class DocumentStorage(Protocol):
    """Хранит canonical PDF и derived artifacts без раскрытия host paths."""

    async def save(self, *, storage_key: str, content: bytes) -> None:
        """Атомарно сохраняет bytes."""

    async def read(self, *, storage_key: str) -> bytes:
        """Читает bytes."""

    async def delete_tree(self, *, storage_prefix: str) -> None:
        """Идемпотентно удаляет document tree."""

    async def is_ready(self) -> bool:
        """Проверяет bounded storage root."""
