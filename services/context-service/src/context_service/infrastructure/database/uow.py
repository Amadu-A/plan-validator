# services/context-service/src/context_service/infrastructure/database/uow.py

"""SQLAlchemy Unit of Work Context Service."""

from types import TracebackType

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from context_service.infrastructure.database.context_repository import (
    SqlAlchemyContextIndexJobRepository,
    SqlAlchemyContextSourceRepository,
    SqlAlchemyProjectContextRepository,
)


class SqlAlchemyContextUnitOfWork:
    """Ограничивает одну application transaction одним AsyncSession."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Сохраняет AsyncSession factory."""
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    @property
    def contexts(self) -> SqlAlchemyProjectContextRepository:
        """Возвращает Project Context repository."""
        return SqlAlchemyProjectContextRepository(self._require_session())

    @property
    def sources(self) -> SqlAlchemyContextSourceRepository:
        """Возвращает Context source repository."""
        return SqlAlchemyContextSourceRepository(self._require_session())

    @property
    def jobs(self) -> SqlAlchemyContextIndexJobRepository:
        """Возвращает durable job repository."""
        return SqlAlchemyContextIndexJobRepository(self._require_session())

    async def __aenter__(
        self,
    ) -> "SqlAlchemyContextUnitOfWork":
        """Открывает новый transaction-scoped session."""
        self._session = self._session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Откатывает незавершённую transaction и закрывает session."""
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
        await self._require_session().commit()

    async def rollback(self) -> None:
        """Откатывает transaction."""
        await self._require_session().rollback()

    def _require_session(self) -> AsyncSession:
        """Возвращает active session либо сообщает programming error."""
        if self._session is None:
            raise RuntimeError("Context Unit of Work is not active")

        return self._session


class SqlAlchemyContextUnitOfWorkFactory:
    """Создаёт независимые Context UoW instances."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Сохраняет shared AsyncSession factory."""
        self._session_factory = session_factory

    def __call__(
        self,
    ) -> SqlAlchemyContextUnitOfWork:
        """Создаёт новый Unit of Work."""
        return SqlAlchemyContextUnitOfWork(self._session_factory)
