# services/auth-service/src/auth_service/infrastructure/database/uow.py

"""SQLAlchemy Unit of Work Authentication Service."""

from types import TracebackType

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from auth_service.infrastructure.database.repositories.session import (
    SqlAlchemySessionRepository,
)
from auth_service.infrastructure.database.repositories.user import (
    SqlAlchemyUserRepository,
)


class SqlAlchemyAuthUnitOfWork:
    """Управляет одной AsyncSession и двумя auth repositories."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Создаёт lazy transaction-scoped AsyncSession."""
        self._session = session_factory()
        self._users = SqlAlchemyUserRepository(self._session)
        self._sessions = SqlAlchemySessionRepository(self._session)
        self._committed = False

    @property
    def users(
        self,
    ) -> SqlAlchemyUserRepository:
        """Возвращает User repository текущего UoW."""
        return self._users

    @property
    def sessions(
        self,
    ) -> SqlAlchemySessionRepository:
        """Возвращает Session repository текущего UoW."""
        return self._sessions

    async def __aenter__(
        self,
    ) -> "SqlAlchemyAuthUnitOfWork":
        """Возвращает открытый transaction scope."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Rollback'ит незавершённый UoW и закрывает AsyncSession."""
        del exc
        del traceback

        if exc_type is not None or not self._committed:
            await self._session.rollback()

        await self._session.close()

    async def commit(self) -> None:
        """Фиксирует transaction и помечает UoW завершённым."""
        await self._session.commit()
        self._committed = True

    async def rollback(self) -> None:
        """Явно откатывает transaction."""
        await self._session.rollback()


class SqlAlchemyAuthUnitOfWorkFactory:
    """Создаёт новый SQLAlchemy UoW на каждый use-case."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Сохраняет shared session factory."""
        self._session_factory = session_factory

    def __call__(
        self,
    ) -> SqlAlchemyAuthUnitOfWork:
        """Создаёт independent transaction scope."""
        return SqlAlchemyAuthUnitOfWork(self._session_factory)
