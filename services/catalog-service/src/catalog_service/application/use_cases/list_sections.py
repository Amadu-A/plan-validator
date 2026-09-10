# services/catalog-service/src/catalog_service/application/use_cases/list_sections.py

"""Use-case чтения пользовательского дерева sections."""

from uuid import UUID

from plan_validator_common.observability import log_execution_time

from catalog_service.application.ports.unit_of_work import CatalogUnitOfWorkFactory
from catalog_service.domain.section import Section


class ListSectionsUseCase:
    """Возвращает user-scoped sections без transport dependency."""

    def __init__(self, uow_factory: CatalogUnitOfWorkFactory) -> None:
        """Сохраняет Unit of Work factory."""
        self._uow_factory = uow_factory

    @log_execution_time("catalog.list_sections")
    async def execute(self, *, user_id: UUID) -> list[Section]:
        """Возвращает все sections пользователя."""
        async with self._uow_factory() as uow:
            return await uow.sections.list_for_user(user_id)
