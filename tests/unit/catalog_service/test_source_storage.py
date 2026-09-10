# tests/unit/catalog_service/test_source_storage.py

"""Unit tests filesystem managed source storage adapter."""

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import pytest
from catalog_service.application.ports.source_storage import SourceStorageError
from catalog_service.infrastructure.storage import LocalSourceStorage


def run_async[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Запускает coroutine без отдельного async pytest plugin."""
    return asyncio.run(coroutine)


def test_local_source_storage_round_trip_and_idempotent_delete(
    tmp_path: Path,
) -> None:
    """Проверяет save/read/delete semantics dedicated storage root."""
    storage = LocalSourceStorage(tmp_path)
    key = "user/N/section/source.pdf"
    content = b"%PDF-1.7\n"

    run_async(
        storage.save(
            storage_key=key,
            content=content,
        )
    )

    assert run_async(storage.read(storage_key=key)) == content

    run_async(storage.delete(storage_key=key))
    run_async(storage.delete(storage_key=key))

    assert not (tmp_path / key).exists()


def test_local_source_storage_rejects_path_escape(
    tmp_path: Path,
) -> None:
    """Проверяет защиту от path traversal даже для internal key."""
    storage = LocalSourceStorage(tmp_path)

    with pytest.raises(SourceStorageError):
        run_async(
            storage.save(
                storage_key="../escape.pdf",
                content=b"%PDF-1.7\n",
            )
        )
