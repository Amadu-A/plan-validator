# services/retrieval-service/src/retrieval_service/infrastructure/database/health.py

"""PostgreSQL health probe Retrieval Service."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class SqlAlchemyDatabaseHealthProbe:
    """Проверяет доступность transaction-scoped Retrieval database."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Сохраняет session factory без открытия connection."""
        self._session_factory = session_factory

    async def ready(self) -> bool:
        """Выполняет lightweight SELECT 1 и возвращает False при ошибке."""
        try:
            async with self._session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            return False

        return True
