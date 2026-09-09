# services/auth-service/src/auth_service/infrastructure/database/health.py

"""Lightweight PostgreSQL readiness adapter."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)


class SqlAlchemyDatabaseHealthProbe:
    """Проверяет database dependency через `SELECT 1`."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Сохраняет session factory для короткого independent probe."""
        self._session_factory = session_factory

    async def is_ready(self) -> bool:
        """Возвращает False при любой database connectivity error."""
        try:
            async with self._session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            return False

        return True
