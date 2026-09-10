# services/retrieval-service/src/retrieval_service/infrastructure/database/uow.py

"""SQLAlchemy Unit of Work Retrieval Service."""

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from retrieval_service.infrastructure.database.repositories.source_index import (
    SqlAlchemySourceIndexRepository,
)


class SqlAlchemyRetrievalUnitOfWork:
    """Управляет одной transaction и Retrieval repositories."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Создаёт transaction-scoped AsyncSession."""
        self._session = session_factory()
        self._source_indexes = SqlAlchemySourceIndexRepository(self._session)
        self._committed = False

    @property
    def source_indexes(self) -> SqlAlchemySourceIndexRepository:
        """Возвращает repository source-index registry."""
        return self._source_indexes

    async def __aenter__(self) -> "SqlAlchemyRetrievalUnitOfWork":
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


class SqlAlchemyRetrievalUnitOfWorkFactory:
    """Создаёт independent Retrieval UoW."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Сохраняет shared session factory."""
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyRetrievalUnitOfWork:
        """Создаёт новый transaction scope."""
        return SqlAlchemyRetrievalUnitOfWork(self._session_factory)
