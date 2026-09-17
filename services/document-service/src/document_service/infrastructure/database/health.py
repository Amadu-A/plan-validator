# services/document-service/src/document_service/infrastructure/database/health.py

"""Database readiness probe Document Service."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class SqlAlchemyDatabaseHealthProbe:
    """Проверяет lightweight SELECT 1."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Сохраняет session factory."""
        self._session_factory = session_factory

    async def is_ready(self) -> bool:
        """Возвращает доступность PostgreSQL."""
        try:
            async with self._session_factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
