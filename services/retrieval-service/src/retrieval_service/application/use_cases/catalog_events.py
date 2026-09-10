# services/retrieval-service/src/retrieval_service/application/use_cases/catalog_events.py

"""Use-cases применения Catalog N/U lifecycle events."""

from datetime import datetime
from uuid import UUID

from plan_validator_common.observability import log_execution_time

from retrieval_service.application.ports.unit_of_work import RetrievalUnitOfWorkFactory
from retrieval_service.application.ports.vector_store import ManagedSourceVectorStore
from retrieval_service.domain.exceptions import RetrievalSourceConflictError
from retrieval_service.domain.source_index import (
    ManagedSourceIndex,
    SourceIndexState,
    SourceKind,
)


def _ensure_same_source_identity(
    *,
    existing: ManagedSourceIndex,
    user_id: UUID,
    section_id: UUID,
    kind: SourceKind,
    source_sha256: str,
) -> None:
    """Не позволяет повторному Catalog event изменить identity source."""
    if (
        existing.user_id != user_id
        or existing.section_id != section_id
        or existing.kind is not kind
        or existing.source_sha256 != source_sha256
    ):
        raise RetrievalSourceConflictError(
            f"Catalog source identity changed for {existing.source_id}"
        )


class RegisterCatalogSourceUseCase:
    """Идемпотентно регистрирует uploaded Catalog source как awaiting_chunks."""

    def __init__(self, uow_factory: RetrievalUnitOfWorkFactory) -> None:
        """Сохраняет Retrieval UoW factory."""
        self._uow_factory = uow_factory

    @log_execution_time("retrieval.register_catalog_source")
    async def execute(
        self,
        *,
        source_id: UUID,
        user_id: UUID,
        section_id: UUID,
        kind: SourceKind,
        original_name: str,
        mime_type: str,
        source_sha256: str,
        occurred_at: datetime,
    ) -> ManagedSourceIndex:
        """Создаёт registry row и не resurrect'ит уже удалённый source."""
        async with self._uow_factory() as uow:
            existing = await uow.source_indexes.get_for_update(source_id)

            if existing is not None:
                _ensure_same_source_identity(
                    existing=existing,
                    user_id=user_id,
                    section_id=section_id,
                    kind=kind,
                    source_sha256=source_sha256,
                )
                return existing

            source = ManagedSourceIndex(
                source_id=source_id,
                user_id=user_id,
                section_id=section_id,
                kind=kind,
                original_name=original_name,
                mime_type=mime_type,
                source_sha256=source_sha256,
                state=SourceIndexState.AWAITING_CHUNKS,
                active_fingerprint=None,
                model_name=None,
                vector_dimension=None,
                chunk_count=0,
                last_error=None,
                created_at=occurred_at,
                updated_at=occurred_at,
                deleted_at=None,
            )
            await uow.source_indexes.add(source)
            await uow.commit()

            return source


class DeleteCatalogSourceUseCase:
    """Сначала исключает source из DB-visible search, затем чистит Qdrant."""

    def __init__(
        self,
        *,
        uow_factory: RetrievalUnitOfWorkFactory,
        vector_store: ManagedSourceVectorStore,
    ) -> None:
        """Сохраняет transaction и vector-store dependencies."""
        self._uow_factory = uow_factory
        self._vector_store = vector_store

    @log_execution_time("retrieval.delete_catalog_source")
    async def execute(
        self,
        *,
        source_id: UUID,
        user_id: UUID,
        section_id: UUID,
        kind: SourceKind,
        original_name: str,
        mime_type: str,
        source_sha256: str,
        occurred_at: datetime,
    ) -> ManagedSourceIndex:
        """Идемпотентно создаёт/обновляет tombstone и повторяет Qdrant cleanup."""
        async with self._uow_factory() as uow:
            source = await uow.source_indexes.get_for_update(source_id)

            if source is None:
                source = ManagedSourceIndex(
                    source_id=source_id,
                    user_id=user_id,
                    section_id=section_id,
                    kind=kind,
                    original_name=original_name,
                    mime_type=mime_type,
                    source_sha256=source_sha256,
                    state=SourceIndexState.DELETED,
                    active_fingerprint=None,
                    model_name=None,
                    vector_dimension=None,
                    chunk_count=0,
                    last_error=None,
                    created_at=occurred_at,
                    updated_at=occurred_at,
                    deleted_at=occurred_at,
                )
                await uow.source_indexes.add(source)
            else:
                _ensure_same_source_identity(
                    existing=source,
                    user_id=user_id,
                    section_id=section_id,
                    kind=kind,
                    source_sha256=source_sha256,
                )
                source = source.mark_deleted(changed_at=occurred_at)
                await uow.source_indexes.save(source)

            await uow.commit()

        await self._vector_store.delete_source(source_id=source_id)

        return source
