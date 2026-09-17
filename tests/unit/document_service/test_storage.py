# tests/unit/document_service/test_storage.py

"""Unit tests bounded filesystem Document storage."""

import asyncio
from pathlib import Path

import pytest
from document_service.infrastructure.storage import LocalDocumentStorage


def test_storage_roundtrip_and_cleanup(tmp_path: Path) -> None:
    """Storage атомарно пишет, читает и удаляет tree."""
    storage = LocalDocumentStorage(tmp_path)
    asyncio.run(storage.save(storage_key=".objects/u/d/original.pdf", content=b"pdf"))
    assert asyncio.run(storage.read(storage_key=".objects/u/d/original.pdf")) == b"pdf"
    asyncio.run(storage.delete_tree(storage_prefix=".objects/u/d"))
    assert not (tmp_path / ".objects/u/d").exists()


def test_storage_rejects_path_escape(tmp_path: Path) -> None:
    """Path traversal не выходит из storage root."""
    storage = LocalDocumentStorage(tmp_path)
    with pytest.raises(ValueError):
        asyncio.run(storage.save(storage_key="../escape", content=b"x"))
