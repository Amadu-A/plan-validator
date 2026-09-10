# services/catalog-service/src/catalog_service/infrastructure/database/engine.py

"""Async SQLAlchemy engine/session factory Catalog Service."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from catalog_service.core.settings import CatalogSettings


def create_catalog_engine(settings: CatalogSettings) -> AsyncEngine:
    """Создаёт bounded PostgreSQL connection pool."""
    return create_async_engine(
        settings.database_url,
        pool_size=settings.catalog_database.pool_size,
        max_overflow=settings.catalog_database.max_overflow,
        pool_timeout=settings.catalog_database.pool_timeout_seconds,
        pool_pre_ping=True,
    )


def create_catalog_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Создаёт transaction-scoped AsyncSession factory."""
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )