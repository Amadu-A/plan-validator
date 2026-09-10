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
    check_readiness: CheckReadinessUseCase

    async def aclose(self) -> None:
        """Освобождает PostgreSQL pool при shutdown."""
        await self.engine.dispose()


def build_container(settings: CatalogSettings) -> CatalogContainer:
    """Собирает concrete infrastructure adapters Catalog Service."""
    engine = create_catalog_engine(settings)
    session_factory = create_catalog_session_factory(engine)
    uow_factory = SqlAlchemyCatalogUnitOfWorkFactory(session_factory)
    clock = SystemClock()

    return CatalogContainer(
        settings=settings,
        engine=engine,
        list_sections=ListSectionsUseCase(uow_factory),
        create_section=CreateSectionUseCase(
            uow_factory=uow_factory,
            clock=clock,
        ),
        update_section=UpdateSectionUseCase(
            uow_factory=uow_factory,
            clock=clock,
        ),
        delete_section=DeleteSectionUseCase(uow_factory),
        get_system_prompt=GetSystemPromptUseCase(uow_factory),
        save_system_prompt=SaveSystemPromptUseCase(
            uow_factory=uow_factory,
            clock=clock,
        ),
        check_readiness=CheckReadinessUseCase(
            SqlAlchemyDatabaseHealthProbe(session_factory)
        ),
    )
