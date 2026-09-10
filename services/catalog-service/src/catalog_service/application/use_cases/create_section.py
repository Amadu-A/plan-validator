# services/catalog-service/src/catalog_service/application/use_cases/create_section.py

"""Use-case создания section каталога."""

from uuid import UUID, uuid4

from plan_validator_common.observability import log_execution_time

from catalog_service.application.ports.clock import Clock
from catalog_service.application.ports.unit_of_work import CatalogUnitOfWorkFactory
from catalog_service.domain.exceptions import SectionNotFoundError
from catalog_service.domain.section import Section, normalize_section_title


class CreateSectionUseCase:
    """Создаёт новый section в ownership scope пользователя."""

    def __init__(
        self,
        *,
        uow_factory: CatalogUnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        """Сохраняет application dependencies."""
        self._uow_factory = uow_factory
        self._clock = clock

    @log_execution_time("catalog.create_section")
    async def execute(
        self,
        *,
        user_id: UUID,
        title: str,
        parent_id: UUID | None,
        sort_order: int,
    ) -> Section:
        """Создаёт section после проверки parent ownership."""
        normalized_title = normalize_section_title(title)
        now = self._clock.now()

        async with self._uow_factory() as uow:
            if parent_id is not None:
                parent = await uow.sections.get_for_user(
                    user_id=user_id,
                    section_id=parent_id,
                )

                if parent is None:
                    raise SectionNotFoundError("Parent section was not found")

            section = Section(
                id=uuid4(),
                user_id=user_id,
                parent_id=parent_id,
                title=normalized_title,
                sort_order=sort_order,
                created_at=now,
                updated_at=now,
            )

            await uow.sections.add(section)
            await uow.commit()

        return section
