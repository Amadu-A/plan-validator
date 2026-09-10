# services/retrieval-service/src/retrieval_service/infrastructure/database/engine.py

"""Async SQLAlchemy engine/session factory Retrieval Service."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from retrieval_service.core.settings import RetrievalSettings


def create_retrieval_engine(settings: RetrievalSettings) -> AsyncEngine:
    """Создаёт bounded PostgreSQL connection pool."""
    return create_async_engine(
        settings.database_url,
        pool_size=settings.retrieval_database.pool_size,
        max_overflow=settings.retrieval_database.max_overflow,
        pool_timeout=settings.retrieval_database.pool_timeout_seconds,
        pool_pre_ping=True,
    )


def create_retrieval_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Создаёт transaction-scoped AsyncSession factory."""
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )
