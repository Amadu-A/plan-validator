# services/document-service/src/document_service/infrastructure/storage.py

"""Filesystem object storage внутри bounded Document root."""

import asyncio
import os
import shutil
from pathlib import Path
from uuid import uuid4


class LocalDocumentStorage:
    """Хранит PDFs/renders с path-traversal protection и atomic writes."""

    def __init__(self, root_dir: Path) -> None:
        """Сохраняет canonical storage root."""
        self._root = root_dir.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, storage_key: str) -> Path:
        """Разрешает только descendants configured root."""
        candidate = (self._root / storage_key).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            raise ValueError("Storage key escapes configured root")
        return candidate

    async def save(self, *, storage_key: str, content: bytes) -> None:
        """Атомарно сохраняет bytes через temporary sibling file."""
        path = self._resolve(storage_key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            await asyncio.to_thread(temporary.write_bytes, content)
            await asyncio.to_thread(os.replace, temporary, path)
        finally:
            if temporary.exists():
                await asyncio.to_thread(temporary.unlink, missing_ok=True)

    async def read(self, *, storage_key: str) -> bytes:
        """Читает bytes внутри bounded root."""
        return await asyncio.to_thread(self._resolve(storage_key).read_bytes)

    async def delete_tree(self, *, storage_prefix: str) -> None:
        """Идемпотентно удаляет directory/object tree."""
        path = self._resolve(storage_prefix)
        if not path.exists():
            return
        if path.is_dir():
            await asyncio.to_thread(shutil.rmtree, path)
        else:
            await asyncio.to_thread(path.unlink, missing_ok=True)

    async def is_ready(self) -> bool:
        """Проверяет bounded write/read/delete probe."""
        probe = self._resolve(f".health/{uuid4().hex}.tmp")
        try:
            await asyncio.to_thread(probe.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(probe.write_bytes, b"ok")
            return await asyncio.to_thread(probe.read_bytes) == b"ok"
        except OSError:
            return False
        finally:
            if probe.exists():
                await asyncio.to_thread(probe.unlink, missing_ok=True)
