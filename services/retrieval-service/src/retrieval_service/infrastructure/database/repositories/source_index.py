# services/retrieval-service/src/retrieval_service/infrastructure/database/
# repositories/source_index.py

"""SQLAlchemy SourceIndexRepository implementation."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from retrieval_service.domain.source_index import (
    ManagedSourceIndex,
    SourceIndexState,
    SourceKind,
    build_version_key,
)
from retrieval_service.infrastructure.database.models.source_index import ManagedSourceIndexModel


class SqlAlchemySourceIndexRepository:
    """Хранит Retrieval source registry и search-visible fingerprints."""

    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет transaction-scoped AsyncSession."""
        self._session = session

    async def add(self, source: ManagedSourceIndex) -> None:
        """Добавляет новый source registry row."""
        self._session.add(self._to_model(source))
        await self._session.flush()

    async def get(self, source_id: UUID) -> ManagedSourceIndex | None:
        """Возвращает source registry row без lock."""
        statement = select(ManagedSourceIndexModel).where(
            ManagedSourceIndexModel.source_id == source_id
        )
        model = await self._session.scalar(statement)

        return self._to_domain(model) if model is not None else None

    async def get_for_update(self, source_id: UUID) -> ManagedSourceIndex | None:
        """Блокирует source registry row для lifecycle switch."""
        statement = (
            select(ManagedSourceIndexModel)
            .where(ManagedSourceIndexModel.source_id == source_id)
            .with_for_update()
        )
        model = await self._session.scalar(statement)

        return self._to_domain(model) if model is not None else None

    async def save(self, source: ManagedSourceIndex) -> None:
        """Сохраняет полное immutable-domain состояние существующего row."""
        statement = (
            update(ManagedSourceIndexModel)
            .where(ManagedSourceIndexModel.source_id == source.source_id)
            .values(
                user_id=source.user_id,
                section_id=source.section_id,
                kind=source.kind.value,
                original_name=source.original_name,
                mime_type=source.mime_type,
                source_sha256=source.source_sha256,
                state=source.state.value,
                active_fingerprint=source.active_fingerprint,
                model_name=source.model_name,
                vector_dimension=source.vector_dimension,
                chunk_count=source.chunk_count,
                last_error=source.last_error,
                created_at=source.created_at,
                updated_at=source.updated_at,
                deleted_at=source.deleted_at,
            )
        )
        await self._session.execute(statement)
        await self._session.flush()

    async def list_active_version_keys(
        self,
        *,
        user_id: UUID,
        kind: SourceKind,
        section_ids: tuple[UUID, ...],
        source_ids: tuple[UUID, ...],
    ) -> tuple[str, ...]:
        """Возвращает exact-filtered active version keys для Qdrant MatchAny."""
        statement = select(
            ManagedSourceIndexModel.source_id,
            ManagedSourceIndexModel.active_fingerprint,
        ).where(
            ManagedSourceIndexModel.user_id == user_id,
            ManagedSourceIndexModel.kind == kind.value,
            ManagedSourceIndexModel.state == SourceIndexState.INDEXED.value,
            ManagedSourceIndexModel.active_fingerprint.is_not(None),
        )

        if section_ids:
            statement = statement.where(ManagedSourceIndexModel.section_id.in_(section_ids))

        if source_ids:
            statement = statement.where(ManagedSourceIndexModel.source_id.in_(source_ids))

        rows = (await self._session.execute(statement)).all()

        return tuple(
            build_version_key(source_id=source_id, fingerprint=fingerprint)
            for source_id, fingerprint in rows
            if fingerprint is not None
        )

    @staticmethod
    def _to_model(source: ManagedSourceIndex) -> ManagedSourceIndexModel:
        """Преобразует immutable domain entity в persistence model."""
        return ManagedSourceIndexModel(
            source_id=source.source_id,
            user_id=source.user_id,
            section_id=source.section_id,
            kind=source.kind.value,
            original_name=source.original_name,
            mime_type=source.mime_type,
            source_sha256=source.source_sha256,
            state=source.state.value,
            active_fingerprint=source.active_fingerprint,
            model_name=source.model_name,
            vector_dimension=source.vector_dimension,
            chunk_count=source.chunk_count,
            last_error=source.last_error,
            created_at=source.created_at,
            updated_at=source.updated_at,
            deleted_at=source.deleted_at,
        )

    @staticmethod
    def _to_domain(model: ManagedSourceIndexModel) -> ManagedSourceIndex:
        """Преобразует persistence model в immutable domain entity."""
        return ManagedSourceIndex(
            source_id=model.source_id,
            user_id=model.user_id,
            section_id=model.section_id,
            kind=SourceKind(model.kind),
            original_name=model.original_name,
            mime_type=model.mime_type,
            source_sha256=model.source_sha256,
            state=SourceIndexState(model.state),
            active_fingerprint=model.active_fingerprint,
            model_name=model.model_name,
            vector_dimension=model.vector_dimension,
            chunk_count=model.chunk_count,
            last_error=model.last_error,
            created_at=model.created_at,
            updated_at=model.updated_at,
            deleted_at=model.deleted_at,
        )
