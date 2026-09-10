# services/catalog-service/src/catalog_service/application/use_cases/delete_section.py

"""Use-case удаления section metadata."""

from uuid import UUID

from plan_validator_common.observability import log_execution_time

from catalog_service.application.ports.unit_of_work import CatalogUnitOfWorkFactory
from catalog_service.domain.exceptions import SectionNotFoundError


class DeleteSectionUseCase:
    """Удаляет section пользователя и его Catalog descendants."""

    def __init__(self, uow_factory: CatalogUnitOfWorkFactory) -> None:
        """Сохраняет Unit of Work factory."""
        self._uow_factory = uow_factory

    @log_execution_time("catalog.delete_section")
    async def execute(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> None:
        """Удаляет только существующий user-owned section."""
        async with self._uow_factory() as uow:
            existing = await uow.sections.get_for_user(
                user_id=user_id,
                section_id=section_id,
            )

            if existing is None:
                raise SectionNotFoundError("Section was not found")

            await uow.sections.delete(
                user_id=user_id,
                section_id=section_id,
            )
            await uow.commit()
