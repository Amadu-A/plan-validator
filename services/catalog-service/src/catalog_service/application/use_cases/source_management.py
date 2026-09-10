# services/catalog-service/src/catalog_service/application/use_cases/source_management.py

"""Use-cases upload/storage/lifecycle managed N/U sources."""

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import PurePath
from uuid import UUID, uuid4
from zipfile import BadZipFile, ZipFile

from plan_validator_common.observability import log_execution_time

from catalog_service.application.ports.clock import Clock
from catalog_service.application.ports.source_storage import (
    SourceStorage,
    SourceStorageError,
)
from catalog_service.application.ports.unit_of_work import CatalogUnitOfWorkFactory
from catalog_service.application.source_tree import (
    restore_user_source_tree_best_effort,
    synchronize_user_source_tree,
)
from catalog_service.domain.exceptions import (
    InvalidManagedSourceUploadError,
    ManagedSourceLifecycleConflictError,
    ManagedSourceNotFoundError,
    ManagedSourceStorageUnavailableError,
    SectionNotFoundError,
)
from catalog_service.domain.section import Section
from catalog_service.domain.source import (
    SOURCE_DELETE_REQUESTED_EVENT,
    SOURCE_UPLOADED_EVENT,
    ManagedSource,
    SourceKind,
    SourceLifecycle,
    SourceOutboxMessage,
    build_source_event_payload,
)

IdentifierFactory = Callable[[], UUID]

MAX_SOURCE_NAME_LENGTH = 255
PDF_EXTENSION = ".pdf"
DOC_EXTENSION = ".doc"
DOCX_EXTENSION = ".docx"
PDF_SIGNATURE_WINDOW = 1024
DOC_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")

SUPPORTED_MIME_BY_EXTENSION = {
    PDF_EXTENSION: "application/pdf",
    DOC_EXTENSION: "application/msword",
    DOCX_EXTENSION: ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
}


@dataclass(frozen=True, slots=True)
class ManagedSourceContent:
    """Application DTO managed source вместе с physical content."""

    source: ManagedSource
    content: bytes


def normalize_source_name(
    original_name: str,
) -> tuple[str, str, str]:
    """Нормализует filename и возвращает имя, extension и canonical MIME."""
    normalized = original_name.replace("\\", "/").rsplit("/", maxsplit=1)[-1].strip()

    if not normalized:
        raise InvalidManagedSourceUploadError("Source filename must not be empty")

    if "\x00" in normalized:
        raise InvalidManagedSourceUploadError("Source filename contains NUL character")

    if len(normalized) > MAX_SOURCE_NAME_LENGTH:
        raise InvalidManagedSourceUploadError(
            f"Source filename must not exceed {MAX_SOURCE_NAME_LENGTH} characters"
        )

    suffix = PurePath(normalized).suffix.casefold()

    if suffix not in SUPPORTED_MIME_BY_EXTENSION:
        raise InvalidManagedSourceUploadError(
            "Only PDF, DOC and DOCX managed sources are supported"
        )

    return (
        normalized,
        suffix,
        SUPPORTED_MIME_BY_EXTENSION[suffix],
    )


def validate_source_content(
    content: bytes,
    *,
    extension: str,
    max_upload_bytes: int,
) -> None:
    """Проверяет bounded size и реальную signature загружаемого файла."""
    if max_upload_bytes <= 0:
        raise InvalidManagedSourceUploadError("Managed source upload limit is invalid")

    if not content:
        raise InvalidManagedSourceUploadError("Managed source content must not be empty")

    if len(content) > max_upload_bytes:
        raise InvalidManagedSourceUploadError("Managed source exceeds the configured upload limit")

    if extension == PDF_EXTENSION:
        if b"%PDF-" not in content[:PDF_SIGNATURE_WINDOW]:
            raise InvalidManagedSourceUploadError("Uploaded file is not a valid PDF")

        return

    if extension == DOC_EXTENSION:
        if not content.startswith(DOC_SIGNATURE):
            raise InvalidManagedSourceUploadError("Uploaded file is not a valid DOC")

        return

    if extension == DOCX_EXTENSION:
        _validate_docx(content)
        return

    raise InvalidManagedSourceUploadError("Unsupported managed source format")


def _validate_docx(content: bytes) -> None:
    """Проверяет минимальную OOXML structure DOCX без извлечения документов."""
    try:
        with ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
    except (BadZipFile, OSError) as exc:
        raise InvalidManagedSourceUploadError("Uploaded DOCX is not a valid OOXML archive") from exc

    required_entries = {
        "[Content_Types].xml",
        "word/document.xml",
    }

    if not required_entries.issubset(names):
        raise InvalidManagedSourceUploadError(
            "Uploaded DOCX does not contain required Word entries"
        )


async def _get_source(
    *,
    uow_factory: CatalogUnitOfWorkFactory,
    user_id: UUID,
    source_id: UUID,
    kind: SourceKind,
) -> ManagedSource:
    """Возвращает source любого lifecycle внутри ownership/kind scope."""
    async with uow_factory() as uow:
        source = await uow.sources.get_for_user_kind(
            user_id=user_id,
            source_id=source_id,
            kind=kind,
        )

    if source is None:
        raise ManagedSourceNotFoundError("Managed source was not found")

    return source


async def _load_user_tree_state(
    *,
    uow_factory: CatalogUnitOfWorkFactory,
    user_id: UUID,
) -> tuple[list[Section], list[ManagedSource]]:
    """Возвращает sections и только active sources для visible tree."""
    async with uow_factory() as uow:
        sections = await uow.sections.list_for_user(user_id)

        sources = await uow.sources.list_active_for_user(
            user_id=user_id,
        )

    return sections, sources


class ListManagedSourcesUseCase:
    """Возвращает managed sources выбранного типа внутри section."""

    def __init__(
        self,
        uow_factory: CatalogUnitOfWorkFactory,
    ) -> None:
        """Сохраняет Unit of Work factory."""
        self._uow_factory = uow_factory

    @log_execution_time("catalog.list_managed_sources")
    async def execute(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
        kind: SourceKind,
    ) -> list[ManagedSource]:
        """Возвращает только не удалённые N либо U sources."""
        async with self._uow_factory() as uow:
            section = await uow.sections.get_for_user(
                user_id=user_id,
                section_id=section_id,
            )

            if section is None:
                raise SectionNotFoundError("Section was not found")

            return await uow.sources.list_for_user_section(
                user_id=user_id,
                section_id=section_id,
                kind=kind,
            )


class UploadManagedSourceUseCase:
    """Сохраняет original, visible mirror, metadata и outbox event."""

    def __init__(
        self,
        *,
        uow_factory: CatalogUnitOfWorkFactory,
        storage: SourceStorage,
        max_upload_bytes: int,
        clock: Clock,
        identifier_factory: IdentifierFactory = uuid4,
    ) -> None:
        """Сохраняет collaborators upload transaction."""
        self._uow_factory = uow_factory
        self._storage = storage
        self._max_upload_bytes = max_upload_bytes
        self._clock = clock
        self._identifier_factory = identifier_factory

    @log_execution_time("catalog.upload_managed_source")
    async def execute(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
        kind: SourceKind,
        original_name: str,
        content: bytes,
    ) -> ManagedSource:
        """Валидирует file и синхронизирует canonical/visible storage."""
        (
            normalized_name,
            extension,
            mime_type,
        ) = normalize_source_name(original_name)

        validate_source_content(
            content,
            extension=extension,
            max_upload_bytes=self._max_upload_bytes,
        )

        sections, active_sources = await _load_user_tree_state(
            uow_factory=self._uow_factory,
            user_id=user_id,
        )

        if not any(section.id == section_id for section in sections):
            raise SectionNotFoundError("Section was not found")

        source_id = self._identifier_factory()
        created_at = self._clock.now()

        storage_key = f".objects/{user_id}/{kind.value}/{source_id}{extension}"

        source = ManagedSource(
            id=source_id,
            user_id=user_id,
            section_id=section_id,
            kind=kind,
            original_name=normalized_name,
            storage_key=storage_key,
            mime_type=mime_type,
            size_bytes=len(content),
            sha256=sha256(content).hexdigest(),
            lifecycle=SourceLifecycle.ACTIVE,
            last_cleanup_error=None,
            created_at=created_at,
            updated_at=created_at,
            deleted_at=None,
        )

        try:
            await self._storage.save(
                storage_key=storage_key,
                content=content,
            )
        except SourceStorageError as exc:
            raise ManagedSourceStorageUnavailableError(
                "Managed source storage is temporarily unavailable"
            ) from exc

        try:
            await synchronize_user_source_tree(
                storage=self._storage,
                user_id=user_id,
                sections=sections,
                sources=[*active_sources, source],
            )
        except Exception:
            with suppress(SourceStorageError):
                await self._storage.delete(
                    storage_key=storage_key,
                )

            await restore_user_source_tree_best_effort(
                storage=self._storage,
                user_id=user_id,
                sections=sections,
                sources=active_sources,
            )
            raise

        message = SourceOutboxMessage(
            id=self._identifier_factory(),
            source_id=source.id,
            event_type=SOURCE_UPLOADED_EVENT,
            payload=build_source_event_payload(source),
            created_at=created_at,
            published_at=None,
            attempt_count=0,
            last_error=None,
        )

        try:
            async with self._uow_factory() as uow:
                section = await uow.sections.get_for_user(
                    user_id=user_id,
                    section_id=section_id,
                )

                if section is None:
                    raise SectionNotFoundError("Section was not found")

                await uow.sources.add(source)
                await uow.source_outbox.add(message)
                await uow.commit()
        except Exception:
            with suppress(SourceStorageError):
                await self._storage.delete(
                    storage_key=storage_key,
                )

            await restore_user_source_tree_best_effort(
                storage=self._storage,
                user_id=user_id,
                sections=sections,
                sources=active_sources,
            )

            raise

        return source


class GetManagedSourceUseCase:
    """Возвращает metadata одного managed source."""

    def __init__(
        self,
        uow_factory: CatalogUnitOfWorkFactory,
    ) -> None:
        """Сохраняет Unit of Work factory."""
        self._uow_factory = uow_factory

    @log_execution_time("catalog.get_managed_source")
    async def execute(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: SourceKind,
    ) -> ManagedSource:
        """Возвращает только логически существующий source."""
        source = await _get_source(
            uow_factory=self._uow_factory,
            user_id=user_id,
            source_id=source_id,
            kind=kind,
        )

        if source.lifecycle is SourceLifecycle.DELETED:
            raise ManagedSourceNotFoundError("Managed source was not found")

        return source


class GetManagedSourceContentUseCase:
    """Возвращает physical content только active managed source."""

    def __init__(
        self,
        *,
        uow_factory: CatalogUnitOfWorkFactory,
        storage: SourceStorage,
    ) -> None:
        """Сохраняет metadata и storage dependencies."""
        self._uow_factory = uow_factory
        self._storage = storage

    @log_execution_time("catalog.get_managed_source_content")
    async def execute(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: SourceKind,
    ) -> ManagedSourceContent:
        """Читает source content без раскрытия internal storage key."""
        source = await _get_source(
            uow_factory=self._uow_factory,
            user_id=user_id,
            source_id=source_id,
            kind=kind,
        )

        if source.lifecycle is SourceLifecycle.DELETED:
            raise ManagedSourceNotFoundError("Managed source was not found")

        if source.lifecycle is not SourceLifecycle.ACTIVE:
            raise ManagedSourceLifecycleConflictError(
                "Managed source content is unavailable during deletion"
            )

        try:
            content = await self._storage.read(
                storage_key=source.storage_key,
            )
        except SourceStorageError as exc:
            raise ManagedSourceStorageUnavailableError(
                "Managed source storage is temporarily unavailable"
            ) from exc

        return ManagedSourceContent(
            source=source,
            content=content,
        )


class DeleteManagedSourceUseCase:
    """Выполняет crash-safe lifecycle удаления canonical и visible source."""

    def __init__(
        self,
        *,
        uow_factory: CatalogUnitOfWorkFactory,
        storage: SourceStorage,
        clock: Clock,
        identifier_factory: IdentifierFactory = uuid4,
    ) -> None:
        """Сохраняет lifecycle collaborators."""
        self._uow_factory = uow_factory
        self._storage = storage
        self._clock = clock
        self._identifier_factory = identifier_factory

    @log_execution_time("catalog.delete_managed_source")
    async def execute(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: SourceKind,
    ) -> None:
        """Удаляет visible mirror, canonical file и подтверждает deleted state."""
        source = await _get_source(
            uow_factory=self._uow_factory,
            user_id=user_id,
            source_id=source_id,
            kind=kind,
        )

        if source.lifecycle is SourceLifecycle.DELETED:
            return

        if source.lifecycle is SourceLifecycle.ACTIVE:
            source = await self._register_delete_intent(source)

        sections, active_sources = await _load_user_tree_state(
            uow_factory=self._uow_factory,
            user_id=user_id,
        )

        try:
            await synchronize_user_source_tree(
                storage=self._storage,
                user_id=user_id,
                sections=sections,
                sources=active_sources,
            )
        except ManagedSourceStorageUnavailableError:
            await self._mark_cleanup_failed(
                source=source,
                error_message="visible_tree_cleanup_failed",
            )
            raise

        try:
            await self._storage.delete(
                storage_key=source.storage_key,
            )
        except SourceStorageError as exc:
            await self._mark_cleanup_failed(
                source=source,
                error_message="storage_delete_failed",
            )

            raise ManagedSourceStorageUnavailableError(
                "Managed source cleanup is temporarily unavailable"
            ) from exc

        deleted = source.mark_deleted(
            changed_at=self._clock.now(),
        )

        async with self._uow_factory() as uow:
            await uow.sources.update(deleted)
            await uow.commit()

    async def _register_delete_intent(
        self,
        source: ManagedSource,
    ) -> ManagedSource:
        """Атомарно сохраняет delete_pending и delete_requested outbox event."""
        changed_at = self._clock.now()

        pending = source.mark_delete_pending(
            changed_at=changed_at,
        )

        message = SourceOutboxMessage(
            id=self._identifier_factory(),
            source_id=pending.id,
            event_type=SOURCE_DELETE_REQUESTED_EVENT,
            payload=build_source_event_payload(pending),
            created_at=changed_at,
            published_at=None,
            attempt_count=0,
            last_error=None,
        )

        async with self._uow_factory() as uow:
            current = await uow.sources.get_for_user_kind_for_update(
                user_id=pending.user_id,
                source_id=pending.id,
                kind=pending.kind,
            )

            if current is None:
                raise ManagedSourceNotFoundError("Managed source was not found")

            if current.lifecycle is SourceLifecycle.DELETED:
                return current

            if current.lifecycle is SourceLifecycle.ACTIVE:
                await uow.sources.update(pending)
                await uow.source_outbox.add(message)
                await uow.commit()
                return pending

            return current

    async def _mark_cleanup_failed(
        self,
        *,
        source: ManagedSource,
        error_message: str,
    ) -> None:
        """Durably фиксирует cleanup_failed для последующего retry."""
        failed = source.mark_cleanup_failed(
            changed_at=self._clock.now(),
            error_message=error_message,
        )

        async with self._uow_factory() as uow:
            await uow.sources.update(failed)
            await uow.commit()
