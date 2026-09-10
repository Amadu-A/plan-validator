# services/catalog-service/src/catalog_service/application/use_cases/update_section.py

"""Use-case изменения title/order/parent section."""

from uuid import UUID

from plan_validator_common.observability import log_execution_time

from catalog_service.application.ports.clock import Clock
from catalog_service.application.ports.unit_of_work import CatalogUnitOfWorkFactory
from catalog_service.domain.exceptions import (
    InvalidSectionHierarchyError,
    SectionNotFoundError,
)
from catalog_service.domain.section import Section, normalize_section_title


class UpdateSectionUseCase:
    """Обновляет section и защищает дерево от циклов."""

    def __init__(
        self,
        *,
        uow_factory: CatalogUnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        """Сохраняет application dependencies."""
        self._uow_factory = uow_factory
        self._clock = clock

    @log_execution_time("catalog.update_section")
    async def execute(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
        title: str | None,
        parent_id: UUID | None,
        parent_id_supplied: bool,
        sort_order: int | None,
    ) -> Section:
        """Обновляет section после проверки ownership и hierarchy."""
        async with self._uow_factory() as uow:
            existing = await uow.sections.get_for_user(
                user_id=user_id,
                section_id=section_id,
            )

            if existing is None:
                raise SectionNotFoundError("Section was not found")

            resolved_parent_id = parent_id if parent_id_supplied else existing.parent_id

            all_sections = await uow.sections.list_for_user(user_id)

            self._validate_parent(
                section_id=section_id,
                parent_id=resolved_parent_id,
                sections=all_sections,
            )

            resolved_title = normalize_section_title(title) if title is not None else existing.title

            updated = Section(
                id=existing.id,
                user_id=existing.user_id,
                parent_id=resolved_parent_id,
                title=resolved_title,
                sort_order=(sort_order if sort_order is not None else existing.sort_order),
                created_at=existing.created_at,
                updated_at=self._clock.now(),
            )

            await uow.sections.update(updated)
            await uow.commit()

        return updated

    @staticmethod
    def _validate_parent(
        *,
        section_id: UUID,
        parent_id: UUID | None,
        sections: list[Section],
    ) -> None:
        """Проверяет существование parent и отсутствие hierarchy cycle."""
        if parent_id is None:
            return

        if parent_id == section_id:
            raise InvalidSectionHierarchyError("Section cannot be its own parent")

        by_id = {section.id: section for section in sections}

        if parent_id not in by_id:
            raise SectionNotFoundError("Parent section was not found")

        current_id: UUID | None = parent_id
        visited: set[UUID] = set()

        while current_id is not None:
            if current_id == section_id:
                raise InvalidSectionHierarchyError("Section cannot be moved below its descendant")

            if current_id in visited:
                raise InvalidSectionHierarchyError("Existing section hierarchy contains a cycle")

            visited.add(current_id)

            current = by_id.get(current_id)
            current_id = current.parent_id if current is not None else None
