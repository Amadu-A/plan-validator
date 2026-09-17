# services/document-service/src/document_service/infrastructure/database/uow.py

"""SQLAlchemy Unit of Work Document Service."""

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from document_service.infrastructure.database.repository import SqlAlchemyProjectDocumentRepository


class SqlAlchemyDocumentUnitOfWork:
    """Ограничивает одну application transaction одним AsyncSession."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Сохраняет session factory."""
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    @property
    def documents(self) -> SqlAlchemyProjectDocumentRepository:
        """Возвращает repository."""
        if self._session is None:
            raise RuntimeError("Document Unit of Work is not active")
        return SqlAlchemyProjectDocumentRepository(self._session)

    async def __aenter__(self) -> "SqlAlchemyDocumentUnitOfWork":
        """Открывает transaction-scoped session."""
        self._session = self._session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Rollback незавершённой transaction и close session."""
        del exc_type, exc, traceback
        if self._session is None:
            return
        try:
            if self._session.in_transaction():
                await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        """Фиксирует transaction."""
        if self._session is None:
            raise RuntimeError("Document Unit of Work is not active")
        await self._session.commit()


class SqlAlchemyDocumentUnitOfWorkFactory:
    """Создаёт независимые UoW instances."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Сохраняет shared session factory."""
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyDocumentUnitOfWork:
        """Создаёт новый transaction scope."""
        return SqlAlchemyDocumentUnitOfWork(self._session_factory)
