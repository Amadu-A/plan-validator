# services/catalog-service/src/catalog_service/application/ports/unit_of_work.py

"""Application Unit of Work contract Catalog Service."""

from types import TracebackType
from typing import Protocol, Self

from catalog_service.application.ports.section_repository import SectionRepository
from catalog_service.application.ports.source_outbox_repository import (
    SourceOutboxRepository,
)
from catalog_service.application.ports.source_repository import ManagedSourceRepository
from catalog_service.application.ports.system_prompt_repository import (
    SystemPromptRepository,
)


class CatalogUnitOfWork(Protocol):
    """Управляет transaction и Catalog repositories."""

    @property
    def sections(self) -> SectionRepository:
        """Возвращает repository sections текущей transaction."""

    @property
    def system_prompts(self) -> SystemPromptRepository:
        """Возвращает repository prompts текущей transaction."""

    @property
    def sources(self) -> ManagedSourceRepository:
        """Возвращает repository managed N/U sources."""

    @property
    def source_outbox(self) -> SourceOutboxRepository:
        """Возвращает transactional outbox repository."""

    async def __aenter__(self) -> Self:
        """Открывает transaction scope."""

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Закрывает transaction с rollback при необходимости."""

    async def commit(self) -> None:
        """Фиксирует текущую transaction."""

    async def rollback(self) -> None:
        """Откатывает текущую transaction."""


class CatalogUnitOfWorkFactory(Protocol):
    """Создаёт новый Catalog Unit of Work."""

    def __call__(self) -> CatalogUnitOfWork:
        """Создаёт независимый transaction scope."""
