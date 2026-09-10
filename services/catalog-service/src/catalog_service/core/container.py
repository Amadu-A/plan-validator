# services/catalog-service/src/catalog_service/core/container.py

"""Composition root Catalog Service."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from catalog_service.application.use_cases import (
    CheckReadinessUseCase,
    CreateSectionUseCase,
    DeleteSectionUseCase,
    GetSystemPromptUseCase,
    ListSectionsUseCase,
    SaveSystemPromptUseCase,
    UpdateSectionUseCase,
)
from catalog_service.application.use_cases.source_management import (
    DeleteManagedSourceUseCase,
    GetManagedSourceContentUseCase,
    GetManagedSourceUseCase,
    ListManagedSourcesUseCase,
    UploadManagedSourceUseCase,
)
from catalog_service.core.settings import CatalogSettings
from catalog_service.infrastructure.clock import SystemClock
from catalog_service.infrastructure.database.engine import (
    create_catalog_engine,
    create_catalog_session_factory,
)
from catalog_service.infrastructure.database.health import (
    SqlAlchemyDatabaseHealthProbe,
)
from catalog_service.infrastructure.database.uow import (
    SqlAlchemyCatalogUnitOfWorkFactory,
)
from catalog_service.infrastructure.storage import LocalSourceStorage


@dataclass(slots=True)
class CatalogContainer:
    """Хранит process-level dependencies Catalog Service."""

    settings: CatalogSettings
    engine: AsyncEngine
    list_sections: ListSectionsUseCase
    create_section: CreateSectionUseCase
    update_section: UpdateSectionUseCase
    delete_section: DeleteSectionUseCase
    get_system_prompt: GetSystemPromptUseCase
    save_system_prompt: SaveSystemPromptUseCase
    list_managed_sources: ListManagedSourcesUseCase
    upload_managed_source: UploadManagedSourceUseCase
    get_managed_source: GetManagedSourceUseCase
    get_managed_source_content: GetManagedSourceContentUseCase
    delete_managed_source: DeleteManagedSourceUseCase
    check_readiness: CheckReadinessUseCase

    async def aclose(self) -> None:
        """Освобождает PostgreSQL pool при shutdown."""
        await self.engine.dispose()


def build_container(
    settings: CatalogSettings,
) -> CatalogContainer:
    """Собирает concrete infrastructure adapters Catalog Service."""
    engine = create_catalog_engine(settings)

    session_factory = create_catalog_session_factory(engine)

    uow_factory = SqlAlchemyCatalogUnitOfWorkFactory(session_factory)

    clock = SystemClock()

    source_storage = LocalSourceStorage(settings.catalog_source_storage.root_dir)

    return CatalogContainer(
        settings=settings,
        engine=engine,
        list_sections=ListSectionsUseCase(uow_factory),
        create_section=CreateSectionUseCase(
            uow_factory=uow_factory,
            clock=clock,
            storage=source_storage,
        ),
        update_section=UpdateSectionUseCase(
            uow_factory=uow_factory,
            clock=clock,
            storage=source_storage,
        ),
        delete_section=DeleteSectionUseCase(
            uow_factory,
            storage=source_storage,
        ),
        get_system_prompt=GetSystemPromptUseCase(uow_factory),
        save_system_prompt=SaveSystemPromptUseCase(
            uow_factory=uow_factory,
            clock=clock,
        ),
        list_managed_sources=ListManagedSourcesUseCase(uow_factory),
        upload_managed_source=UploadManagedSourceUseCase(
            uow_factory=uow_factory,
            storage=source_storage,
            max_upload_bytes=(settings.catalog_source_storage.max_upload_bytes),
            clock=clock,
        ),
        get_managed_source=GetManagedSourceUseCase(uow_factory),
        get_managed_source_content=GetManagedSourceContentUseCase(
            uow_factory=uow_factory,
            storage=source_storage,
        ),
        delete_managed_source=DeleteManagedSourceUseCase(
            uow_factory=uow_factory,
            storage=source_storage,
            clock=clock,
        ),
        check_readiness=CheckReadinessUseCase(SqlAlchemyDatabaseHealthProbe(session_factory)),
    )
