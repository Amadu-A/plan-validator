# services/catalog-service/src/catalog_service/infrastructure/database/uow.py

"""SQLAlchemy Unit of Work Catalog Service."""

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog_service.infrastructure.database.repositories.section import (
    SqlAlchemySectionRepository,
)
from catalog_service.infrastructure.database.repositories.source import (
    SqlAlchemyManagedSourceRepository,
)
from catalog_service.infrastructure.database.repositories.source_outbox import (
    SqlAlchemySourceOutboxRepository,
)
from catalog_service.infrastructure.database.repositories.system_prompt import (
    SqlAlchemySystemPromptRepository,
)


class SqlAlchemyCatalogUnitOfWork:
    """Управляет одной transaction и Catalog repositories."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Создаёт transaction-scoped AsyncSession."""
        self._session = session_factory()
        self._sections = SqlAlchemySectionRepository(self._session)
        self._system_prompts = SqlAlchemySystemPromptRepository(self._session)
        self._sources = SqlAlchemyManagedSourceRepository(self._session)
        self._source_outbox = SqlAlchemySourceOutboxRepository(self._session)
        self._committed = False

    @property
    def sections(self) -> SqlAlchemySectionRepository:
        """Возвращает repository sections."""
        return self._sections

    @property
    def system_prompts(self) -> SqlAlchemySystemPromptRepository:
        """Возвращает repository prompts."""
        return self._system_prompts

    @property
    def sources(self) -> SqlAlchemyManagedSourceRepository:
        """Возвращает repository managed N/U sources."""
        return self._sources

    @property
    def source_outbox(self) -> SqlAlchemySourceOutboxRepository:
        """Возвращает transactional source outbox repository."""
        return self._source_outbox

    async def __aenter__(self) -> "SqlAlchemyCatalogUnitOfWork":
        """Открывает transaction scope."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Rollback'ит незавершённую transaction и закрывает session."""
        del exc
        del traceback

        if exc_type is not None or not self._committed:
            await self._session.rollback()

        await self._session.close()

    async def commit(self) -> None:
        """Фиксирует transaction."""
        await self._session.commit()
        self._committed = True

    async def rollback(self) -> None:
        """Явно откатывает transaction."""
        await self._session.rollback()


class SqlAlchemyCatalogUnitOfWorkFactory:
    """Создаёт independent Catalog UoW."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Сохраняет shared session factory."""
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyCatalogUnitOfWork:
        """Создаёт новый transaction scope."""
        return SqlAlchemyCatalogUnitOfWork(self._session_factory)
