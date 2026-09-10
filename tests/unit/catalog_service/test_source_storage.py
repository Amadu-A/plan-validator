# tests/unit/catalog_service/test_source_storage.py

"""Unit tests filesystem managed source storage adapter."""

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from catalog_service.application.ports.source_storage import (
    SourceStorageError,
)
from catalog_service.domain.section import Section
from catalog_service.domain.source import (
    ManagedSource,
    SourceKind,
    SourceLifecycle,
)
from catalog_service.infrastructure.storage import LocalSourceStorage

NOW = datetime(
    2026,
    9,
    10,
    tzinfo=UTC,
)


def run_async[T](
    coroutine: Coroutine[Any, Any, T],
) -> T:
    """Запускает coroutine без отдельного async pytest plugin."""
    return asyncio.run(coroutine)


def test_local_source_storage_round_trip_and_idempotent_delete(
    tmp_path: Path,
) -> None:
    """Проверяет canonical save/read/delete semantics."""
    storage = LocalSourceStorage(tmp_path)

    key = ".objects/11111111-1111-1111-1111-111111111111/N/source.pdf"

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


def test_visible_tree_matches_nested_catalog_and_contains_source(
    tmp_path: Path,
) -> None:
    """Проверяет зеркало sections и N/U документов на filesystem."""
    storage = LocalSourceStorage(tmp_path)

    user_id = UUID("11111111-1111-1111-1111-111111111111")

    root_id = UUID("22222222-2222-2222-2222-222222222222")

    child_id = UUID("33333333-3333-3333-3333-333333333333")

    source_id = UUID("44444444-4444-4444-4444-444444444444")

    root = Section(
        id=root_id,
        user_id=user_id,
        parent_id=None,
        title="Нормативная база",
        sort_order=0,
        created_at=NOW,
        updated_at=NOW,
    )

    child = Section(
        id=child_id,
        user_id=user_id,
        parent_id=root_id,
        title="Электроснабжение",
        sort_order=0,
        created_at=NOW,
        updated_at=NOW,
    )

    storage_key = f".objects/{user_id}/N/{source_id}.pdf"

    source = ManagedSource(
        id=source_id,
        user_id=user_id,
        section_id=child_id,
        kind=SourceKind.NORMATIVE,
        original_name="СП 48.13330.pdf",
        storage_key=storage_key,
        mime_type="application/pdf",
        size_bytes=9,
        sha256="a" * 64,
        lifecycle=SourceLifecycle.ACTIVE,
        last_cleanup_error=None,
        created_at=NOW,
        updated_at=NOW,
        deleted_at=None,
    )

    content = b"%PDF-1.7"

    run_async(
        storage.save(
            storage_key=storage_key,
            content=content,
        )
    )

    run_async(
        storage.synchronize_user_tree(
            user_id=user_id,
            sections=[
                root,
                child,
            ],
            sources=[
                source,
            ],
        )
    )

    user_root = tmp_path / "users" / str(user_id)

    root_directories = list(user_root.glob("Нормативная база__*"))

    assert len(root_directories) == 1

    root_directory = root_directories[0]

    child_directories = list(root_directory.glob("Электроснабжение__*"))

    assert len(child_directories) == 1

    child_directory = child_directories[0]

    assert (child_directory / "N_Нормативные документы").is_dir()

    assert (child_directory / "U_Пользовательские документы").is_dir()

    mirrored_files = list((child_directory / "N_Нормативные документы").glob("СП 48.13330__*.pdf"))

    assert len(mirrored_files) == 1

    assert mirrored_files[0].read_bytes() == content
