# services/catalog-service/src/catalog_service/application/use_cases/delete_section.py

"""Use-case удаления section metadata и filesystem directory tree."""

from uuid import UUID

from plan_validator_common.observability import log_execution_time

from catalog_service.application.ports.source_storage import SourceStorage
from catalog_service.application.ports.unit_of_work import CatalogUnitOfWorkFactory
from catalog_service.application.source_tree import (
    restore_user_source_tree_best_effort,
    synchronize_user_source_tree,
)
from catalog_service.domain.exceptions import (
    SectionContainsSourcesError,
    SectionNotFoundError,
)
from catalog_service.domain.section import Section


class DeleteSectionUseCase:
    """Удаляет section только после cleanup managed sources."""

    def __init__(
        self,
        uow_factory: CatalogUnitOfWorkFactory,
        storage: SourceStorage | None = None,
    ) -> None:
        """Сохраняет application dependencies."""
        self._uow_factory = uow_factory
        self._storage = storage

    @log_execution_time("catalog.delete_section")
    async def execute(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> None:
        """Удаляет DB subtree и corresponding filesystem directories."""
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

            all_sections = await uow.sections.list_for_user(user_id)

            active_sources = (
                await uow.sources.list_active_for_user(
                    user_id=user_id,
                )
                if self._storage is not None
                else []
            )

            removed_ids = self._subtree_ids(
                root_id=section_id,
                sections=all_sections,
            )

            remaining_sections = [
                section for section in all_sections if section.id not in removed_ids
            ]

            tree_synchronized = False

            if self._storage is not None:
                await synchronize_user_source_tree(
                    storage=self._storage,
                    user_id=user_id,
                    sections=remaining_sections,
                    sources=active_sources,
                )
                tree_synchronized = True

            try:
                await uow.sources.purge_deleted_in_subtree(
                    user_id=user_id,
                    section_id=section_id,
                )

                await uow.sections.delete(
                    user_id=user_id,
                    section_id=section_id,
                )

                await uow.commit()
            except Exception:
                if self._storage is not None and tree_synchronized:
                    await restore_user_source_tree_best_effort(
                        storage=self._storage,
                        user_id=user_id,
                        sections=all_sections,
                        sources=active_sources,
                    )

                raise

    @staticmethod
    def _subtree_ids(
        *,
        root_id: UUID,
        sections: list[Section],
    ) -> set[UUID]:
        """Возвращает IDs root section и всех её descendants."""
        result = {root_id}
        changed = True

        while changed:
            changed = False

            for section in sections:
                if section.parent_id in result and section.id not in result:
                    result.add(section.id)
                    changed = True

        return result
