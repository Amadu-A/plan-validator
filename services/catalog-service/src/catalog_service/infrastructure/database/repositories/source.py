# services/catalog-service/src/catalog_service/infrastructure/database/repositories/source.py

"""SQLAlchemy implementation ManagedSourceRepository."""

from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from catalog_service.domain.source import ManagedSource, SourceKind, SourceLifecycle
from catalog_service.infrastructure.database.models.section import SectionModel
from catalog_service.infrastructure.database.models.source import ManagedSourceModel


class SqlAlchemyManagedSourceRepository:
    """Реализует persistence managed source aggregate."""

    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет transaction-scoped AsyncSession."""
        self._session = session

    async def list_for_user_section(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
        kind: SourceKind,
    ) -> list[ManagedSource]:
        """Возвращает не удалённые sources одной user-owned section."""
        statement = (
            select(ManagedSourceModel)
            .where(
                ManagedSourceModel.user_id == user_id,
                ManagedSourceModel.section_id == section_id,
                ManagedSourceModel.kind == kind.value,
                ManagedSourceModel.lifecycle != SourceLifecycle.DELETED.value,
            )
            .order_by(
                ManagedSourceModel.created_at.desc(),
                ManagedSourceModel.original_name,
                ManagedSourceModel.id,
            )
        )

        models = (await self._session.scalars(statement)).all()

        return [self._to_domain(model) for model in models]

    async def get_for_user_kind(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: SourceKind,
    ) -> ManagedSource | None:
        """Возвращает source любого lifecycle внутри ownership/kind scope."""
        statement = select(ManagedSourceModel).where(
            ManagedSourceModel.id == source_id,
            ManagedSourceModel.user_id == user_id,
            ManagedSourceModel.kind == kind.value,
        )

        model = await self._session.scalar(statement)

        return self._to_domain(model) if model is not None else None

    async def get_for_user_kind_for_update(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: SourceKind,
    ) -> ManagedSource | None:
        """Возвращает source с PostgreSQL row lock."""
        statement = (
            select(ManagedSourceModel)
            .where(
                ManagedSourceModel.id == source_id,
                ManagedSourceModel.user_id == user_id,
                ManagedSourceModel.kind == kind.value,
            )
            .with_for_update()
        )

        model = await self._session.scalar(statement)

        return self._to_domain(model) if model is not None else None

    async def add(self, source: ManagedSource) -> None:
        """Добавляет managed source metadata."""
        self._session.add(
            ManagedSourceModel(
                id=source.id,
                user_id=source.user_id,
                section_id=source.section_id,
                kind=source.kind.value,
                original_name=source.original_name,
                storage_key=source.storage_key,
                mime_type=source.mime_type,
                size_bytes=source.size_bytes,
                sha256=source.sha256,
                lifecycle=source.lifecycle.value,
                last_cleanup_error=source.last_cleanup_error,
                created_at=source.created_at,
                updated_at=source.updated_at,
                deleted_at=source.deleted_at,
            )
        )

        await self._session.flush()

    async def update(self, source: ManagedSource) -> None:
        """Обновляет lifecycle mutable fields source."""
        statement = (
            update(ManagedSourceModel)
            .where(
                ManagedSourceModel.id == source.id,
                ManagedSourceModel.user_id == source.user_id,
                ManagedSourceModel.kind == source.kind.value,
            )
            .values(
                lifecycle=source.lifecycle.value,
                last_cleanup_error=source.last_cleanup_error,
                updated_at=source.updated_at,
                deleted_at=source.deleted_at,
            )
        )

        await self._session.execute(statement)

    async def has_live_in_subtree(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> bool:
        """Проверяет live source через recursive section CTE."""
        section_tree = (
            select(SectionModel.id.label("id"))
            .where(
                SectionModel.id == section_id,
                SectionModel.user_id == user_id,
            )
            .cte(
                "catalog_section_tree",
                recursive=True,
            )
        )

        section_tree = section_tree.union_all(
            select(SectionModel.id.label("id"))
            .join(
                section_tree,
                SectionModel.parent_id == section_tree.c.id,
            )
            .where(SectionModel.user_id == user_id)
        )

        statement = (
            select(ManagedSourceModel.id)
            .where(
                ManagedSourceModel.user_id == user_id,
                ManagedSourceModel.section_id.in_(select(section_tree.c.id)),
                ManagedSourceModel.lifecycle != SourceLifecycle.DELETED.value,
            )
            .limit(1)
        )

        return await self._session.scalar(statement) is not None

    async def purge_deleted_in_subtree(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> None:
        """Удаляет только deleted metadata, чтобы FK RESTRICT не мешал section delete."""
        section_tree = (
            select(SectionModel.id.label("id"))
            .where(
                SectionModel.id == section_id,
                SectionModel.user_id == user_id,
            )
            .cte(
                "catalog_deleted_section_tree",
                recursive=True,
            )
        )

        section_tree = section_tree.union_all(
            select(SectionModel.id.label("id"))
            .join(
                section_tree,
                SectionModel.parent_id == section_tree.c.id,
            )
            .where(SectionModel.user_id == user_id)
        )

        statement = delete(ManagedSourceModel).where(
            ManagedSourceModel.user_id == user_id,
            ManagedSourceModel.section_id.in_(select(section_tree.c.id)),
            ManagedSourceModel.lifecycle == SourceLifecycle.DELETED.value,
        )

        await self._session.execute(statement)

    @staticmethod
    def _to_domain(model: ManagedSourceModel) -> ManagedSource:
        """Преобразует persistence model в immutable domain entity."""
        return ManagedSource(
            id=model.id,
            user_id=model.user_id,
            section_id=model.section_id,
            kind=SourceKind(model.kind),
            original_name=model.original_name,
            storage_key=model.storage_key,
            mime_type=model.mime_type,
            size_bytes=model.size_bytes,
            sha256=model.sha256,
            lifecycle=SourceLifecycle(model.lifecycle),
            last_cleanup_error=model.last_cleanup_error,
            created_at=model.created_at,
            updated_at=model.updated_at,
            deleted_at=model.deleted_at,
        )
