# services/catalog-service/src/catalog_service/application/use_cases/delete_section.py

"""Use-case удаления section metadata."""

from uuid import UUID

from plan_validator_common.observability import log_execution_time

from catalog_service.application.ports.unit_of_work import CatalogUnitOfWorkFactory
from catalog_service.domain.exceptions import (
    SectionContainsSourcesError,
    SectionNotFoundError,
)


class DeleteSectionUseCase:
    """Удаляет section пользователя только после cleanup managed sources."""

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
        """Удаляет section subtree, если в нём нет живых N/U sources."""
        async with self._uow_factory() as uow:
            existing = await uow.sections.get_for_user(
                user_id=user_id,
                section_id=section_id,
            )

            if existing is None:
                raise SectionNotFoundError("Section was not found")

            has_live_sources = await uow.sources.has_live_in_subtree(
                user_id=user_id,
                section_id=section_id,
            )

            if has_live_sources:
                raise SectionContainsSourcesError(
                    "Section contains managed sources and cannot be deleted"
                )

            await uow.sources.purge_deleted_in_subtree(
                user_id=user_id,
                section_id=section_id,
            )
            await uow.sections.delete(
                user_id=user_id,
                section_id=section_id,
            )
            await uow.commit()
