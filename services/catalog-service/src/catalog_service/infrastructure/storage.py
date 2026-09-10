# services/catalog-service/src/catalog_service/infrastructure/storage.py

"""Filesystem adapter persistent managed source storage."""

import asyncio
import os
import tempfile
from pathlib import Path, PurePosixPath

from catalog_service.application.ports.source_storage import SourceStorageError


class LocalSourceStorage:
    """Хранит managed sources внутри dedicated persistent filesystem root."""

    def __init__(self, root_dir: Path) -> None:
        """Сохраняет canonical storage root без создания side effects."""
        self._root_dir = root_dir

    async def save(self, *, storage_key: str, content: bytes) -> None:
        """Атомарно сохраняет bytes через temporary file + os.replace."""
        await asyncio.to_thread(
            self._save_sync,
            storage_key,
            content,
        )

    async def read(self, *, storage_key: str) -> bytes:
        """Читает bytes storage object вне event loop."""
        return await asyncio.to_thread(
            self._read_sync,
            storage_key,
        )

    async def delete(self, *, storage_key: str) -> None:
        """Идемпотентно удаляет storage object вне event loop."""
        await asyncio.to_thread(
            self._delete_sync,
            storage_key,
        )

    def _resolve_path(self, storage_key: str) -> Path:
        """Проверяет, что внутренний key остаётся внутри storage root."""
        if not storage_key or "\\" in storage_key:
            raise SourceStorageError("Invalid managed source storage key")

        relative = PurePosixPath(storage_key)

        if relative.is_absolute() or ".." in relative.parts:
            raise SourceStorageError("Invalid managed source storage key")

        root = self._root_dir.resolve()
        target = root.joinpath(*relative.parts).resolve()

        try:
            target.relative_to(root)
        except ValueError as exc:
            raise SourceStorageError("Managed source path escapes storage root") from exc

        return target

    def _save_sync(self, storage_key: str, content: bytes) -> None:
        """Выполняет synchronous atomic file save."""
        target = self._resolve_path(storage_key)

        try:
            target.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.",
                suffix=".tmp",
                dir=target.parent,
            )

            try:
                with os.fdopen(descriptor, "wb") as temporary_file:
                    temporary_file.write(content)
                    temporary_file.flush()
                    os.fsync(temporary_file.fileno())

                os.replace(
                    temporary_name,
                    target,
                )
            finally:
                Path(temporary_name).unlink(missing_ok=True)
        except OSError as exc:
            raise SourceStorageError("Failed to save managed source") from exc

    def _read_sync(self, storage_key: str) -> bytes:
        """Выполняет synchronous bounded file read по trusted storage key."""
        target = self._resolve_path(storage_key)

        try:
            return target.read_bytes()
        except OSError as exc:
            raise SourceStorageError("Failed to read managed source") from exc

    def _delete_sync(self, storage_key: str) -> None:
        """Выполняет synchronous idempotent file delete."""
        target = self._resolve_path(storage_key)

        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise SourceStorageError("Failed to delete managed source") from exc
