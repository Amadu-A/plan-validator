# tests/unit/catalog_service/test_source_management.py

"""Unit tests Stage 7 managed N/U source use-cases."""

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from catalog_service.application.ports.source_storage import SourceStorageError
from catalog_service.application.use_cases.create_section import CreateSectionUseCase
from catalog_service.application.use_cases.delete_section import DeleteSectionUseCase
from catalog_service.application.use_cases.source_management import (
    DeleteManagedSourceUseCase,
    GetManagedSourceContentUseCase,
    ListManagedSourcesUseCase,
    UploadManagedSourceUseCase,
)
from catalog_service.domain.exceptions import (
    InvalidManagedSourceUploadError,
    ManagedSourceStorageUnavailableError,
    SectionContainsSourcesError,
)
from catalog_service.domain.source import (
    SOURCE_DELETE_REQUESTED_EVENT,
    SOURCE_UPLOADED_EVENT,
    SourceKind,
    SourceLifecycle,
)

from tests.unit.catalog_service.fakes import FakeUnitOfWorkFactory, FixedClock

NOW = datetime(2026, 9, 10, 7, 0, tzinfo=UTC)


def run_async[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Запускает coroutine без отдельного async pytest plugin."""
    return asyncio.run(coroutine)


class MemorySourceStorage:
    """In-memory SourceStorage с управляемой ошибкой delete."""

    def __init__(self) -> None:
        """Создаёт пустой physical object store."""
        self.objects: dict[str, bytes] = {}
        self.fail_next_delete = False

    async def save(self, *, storage_key: str, content: bytes) -> None:
        """Сохраняет bytes."""
        self.objects[storage_key] = content

    async def read(self, *, storage_key: str) -> bytes:
        """Возвращает bytes либо storage error."""
        try:
            return self.objects[storage_key]
        except KeyError as exc:
            raise SourceStorageError("missing") from exc

    async def delete(self, *, storage_key: str) -> None:
        """Удаляет bytes и умеет один раз имитировать storage failure."""
        if self.fail_next_delete:
            self.fail_next_delete = False
            raise SourceStorageError("temporary failure")

        self.objects.pop(storage_key, None)

    async def synchronize_user_tree(
        self,
        *,
        user_id: UUID,
        sections: list[object],
        sources: list[object],
    ) -> None:
        """Fake storage не materialize'ит visible filesystem tree."""
        del user_id
        del sections
        del sources


def build_source_use_cases() -> tuple[
    FakeUnitOfWorkFactory,
    MemorySourceStorage,
    CreateSectionUseCase,
    DeleteSectionUseCase,
    UploadManagedSourceUseCase,
    ListManagedSourcesUseCase,
    GetManagedSourceContentUseCase,
    DeleteManagedSourceUseCase,
]:
    """Собирает source use-cases поверх deterministic fakes."""
    factory = FakeUnitOfWorkFactory()
    storage = MemorySourceStorage()
    clock = FixedClock(NOW)

    return (
        factory,
        storage,
        CreateSectionUseCase(
            uow_factory=factory,
            clock=clock,
        ),
        DeleteSectionUseCase(factory),
        UploadManagedSourceUseCase(
            uow_factory=factory,
            storage=storage,
            max_upload_bytes=1024 * 1024,
            clock=clock,
        ),
        ListManagedSourcesUseCase(factory),
        GetManagedSourceContentUseCase(
            uow_factory=factory,
            storage=storage,
        ),
        DeleteManagedSourceUseCase(
            uow_factory=factory,
            storage=storage,
            clock=clock,
        ),
    )


def create_section(
    *,
    create: CreateSectionUseCase,
    user_id: UUID,
) -> UUID:
    """Создаёт test section и возвращает её UUID."""
    section = run_async(
        create.execute(
            user_id=user_id,
            title="Нормативная база",
            parent_id=None,
            sort_order=0,
        )
    )

    return section.id


def test_upload_separates_n_and_u_and_creates_outbox() -> None:
    """Проверяет semantic kind, storage, SHA и durable upload events."""
    (
        factory,
        storage,
        create,
        _,
        upload,
        list_sources,
        get_content,
        _,
    ) = build_source_use_cases()

    user_id = UUID("11111111-1111-1111-1111-111111111111")
    section_id = create_section(create=create, user_id=user_id)
    pdf = b"%PDF-1.7\nstage-7\n"

    normative = run_async(
        upload.execute(
            user_id=user_id,
            section_id=section_id,
            kind=SourceKind.NORMATIVE,
            original_name="СП 1.pdf",
            content=pdf,
        )
    )
    user_source = run_async(
        upload.execute(
            user_id=user_id,
            section_id=section_id,
            kind=SourceKind.USER,
            original_name="Письмо.pdf",
            content=pdf,
        )
    )

    n_values = run_async(
        list_sources.execute(
            user_id=user_id,
            section_id=section_id,
            kind=SourceKind.NORMATIVE,
        )
    )
    u_values = run_async(
        list_sources.execute(
            user_id=user_id,
            section_id=section_id,
            kind=SourceKind.USER,
        )
    )

    assert [value.id for value in n_values] == [normative.id]
    assert [value.id for value in u_values] == [user_source.id]
    assert normative.storage_key in storage.objects
    assert len(normative.sha256) == 64
    assert normative.sha256 == user_source.sha256
    assert {message.event_type for message in factory.source_outbox.values()} == {
        SOURCE_UPLOADED_EVENT
    }

    content = run_async(
        get_content.execute(
            user_id=user_id,
            source_id=normative.id,
            kind=SourceKind.NORMATIVE,
        )
    )

    assert content.content == pdf
    assert content.source.id == normative.id


def test_invalid_pdf_signature_is_rejected_before_storage() -> None:
    """Проверяет content signature validation до side effects."""
    (
        factory,
        storage,
        create,
        _,
        upload,
        _,
        _,
        _,
    ) = build_source_use_cases()

    user_id = UUID("22222222-2222-2222-2222-222222222222")
    section_id = create_section(create=create, user_id=user_id)

    with pytest.raises(InvalidManagedSourceUploadError):
        run_async(
            upload.execute(
                user_id=user_id,
                section_id=section_id,
                kind=SourceKind.NORMATIVE,
                original_name="fake.pdf",
                content=b"not-a-pdf",
            )
        )

    assert not storage.objects
    assert not factory.sources
    assert not factory.source_outbox


def test_delete_is_idempotent_and_section_is_protected_until_cleanup() -> None:
    """Проверяет delete lifecycle и запрет orphan-producing section delete."""
    (
        factory,
        storage,
        create,
        delete_section,
        upload,
        _,
        _,
        delete_source,
    ) = build_source_use_cases()

    user_id = UUID("33333333-3333-3333-3333-333333333333")
    section_id = create_section(create=create, user_id=user_id)

    source = run_async(
        upload.execute(
            user_id=user_id,
            section_id=section_id,
            kind=SourceKind.NORMATIVE,
            original_name="СП.pdf",
            content=b"%PDF-1.7\n",
        )
    )

    with pytest.raises(SectionContainsSourcesError):
        run_async(
            delete_section.execute(
                user_id=user_id,
                section_id=section_id,
            )
        )

    run_async(
        delete_source.execute(
            user_id=user_id,
            source_id=source.id,
            kind=SourceKind.NORMATIVE,
        )
    )
    run_async(
        delete_source.execute(
            user_id=user_id,
            source_id=source.id,
            kind=SourceKind.NORMATIVE,
        )
    )

    assert factory.sources[source.id].lifecycle is SourceLifecycle.DELETED
    assert source.storage_key not in storage.objects
    assert [message.event_type for message in factory.source_outbox.values()].count(
        SOURCE_DELETE_REQUESTED_EVENT
    ) == 1

    run_async(
        delete_section.execute(
            user_id=user_id,
            section_id=section_id,
        )
    )

    assert section_id not in factory.sections
    assert source.id not in factory.sources


def test_cleanup_failure_is_durable_and_retryable() -> None:
    """Проверяет cleanup_failed state и успешный повтор delete."""
    (
        factory,
        storage,
        create,
        _,
        upload,
        _,
        _,
        delete_source,
    ) = build_source_use_cases()

    user_id = UUID("44444444-4444-4444-4444-444444444444")
    section_id = create_section(create=create, user_id=user_id)

    source = run_async(
        upload.execute(
            user_id=user_id,
            section_id=section_id,
            kind=SourceKind.USER,
            original_name="Акт.pdf",
            content=b"%PDF-1.7\n",
        )
    )

    storage.fail_next_delete = True

    with pytest.raises(ManagedSourceStorageUnavailableError):
        run_async(
            delete_source.execute(
                user_id=user_id,
                source_id=source.id,
                kind=SourceKind.USER,
            )
        )

    assert factory.sources[source.id].lifecycle is SourceLifecycle.CLEANUP_FAILED

    run_async(
        delete_source.execute(
            user_id=user_id,
            source_id=source.id,
            kind=SourceKind.USER,
        )
    )

    assert factory.sources[source.id].lifecycle is SourceLifecycle.DELETED
