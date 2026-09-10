# services/catalog-service/src/catalog_service/infrastructure/database/health.py

"""Lightweight PostgreSQL readiness adapter Catalog Service."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class SqlAlchemyDatabaseHealthProbe:
    """Проверяет PostgreSQL через короткий `SELECT 1`."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Сохраняет shared session factory."""
        self._session_factory = session_factory

    async def is_ready(self) -> bool:
        """Возвращает False при database connectivity failure."""
        try:
            async with self._session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            return False

        return True
