# services/catalog-service/src/catalog_service/infrastructure/database/repositories/section.py

"""SQLAlchemy implementation SectionRepository."""

from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from catalog_service.domain.section import Section
from catalog_service.infrastructure.database.models.section import SectionModel


class SqlAlchemySectionRepository:
    """Реализует persistence только user sections."""

    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет transaction-scoped AsyncSession."""
        self._session = session

    async def list_for_user(self, user_id: UUID) -> list[Section]:
        """Возвращает sections пользователя в stable display order."""
        statement = (
            select(SectionModel)
            .where(SectionModel.user_id == user_id)
            .order_by(
                SectionModel.sort_order,
                SectionModel.title,
                SectionModel.id,
            )
        )

        models = (await self._session.scalars(statement)).all()

        return [self._to_domain(model) for model in models]

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> Section | None:
        """Возвращает section только при совпадении owner."""
        statement = select(SectionModel).where(
            SectionModel.id == section_id,
            SectionModel.user_id == user_id,
        )

        model = await self._session.scalar(statement)

        return self._to_domain(model) if model is not None else None

    async def add(self, section: Section) -> None:
        """Добавляет section в текущую transaction."""
        self._session.add(
            SectionModel(
                id=section.id,
                user_id=section.user_id,
                parent_id=section.parent_id,
                title=section.title,
                sort_order=section.sort_order,
                created_at=section.created_at,
                updated_at=section.updated_at,
            )
        )

        await self._session.flush()

    async def update(self, section: Section) -> None:
        """Обновляет mutable поля user-owned section."""
        statement = (
            update(SectionModel)
            .where(
                SectionModel.id == section.id,
                SectionModel.user_id == section.user_id,
            )
            .values(
                parent_id=section.parent_id,
                title=section.title,
                sort_order=section.sort_order,
                updated_at=section.updated_at,
            )
        )

        await self._session.execute(statement)

    async def delete(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> None:
        """Удаляет section и полагается на FK cascade для descendants."""
        statement = delete(SectionModel).where(
            SectionModel.id == section_id,
            SectionModel.user_id == user_id,
        )

        await self._session.execute(statement)

    @staticmethod
    def _to_domain(model: SectionModel) -> Section:
        """Преобразует SQLAlchemy model в Domain Section."""
        return Section(
            id=model.id,
            user_id=model.user_id,
            parent_id=model.parent_id,
            title=model.title,
            sort_order=model.sort_order,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )