# services/document-service/src/document_service/infrastructure/database/engine.py

"""SQLAlchemy async engine/session factory Document Service."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from document_service.core.settings import DocumentSettings


def create_document_engine(settings: DocumentSettings) -> AsyncEngine:
    """Создаёт process-level async engine."""
    database = settings.document_database
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=database.pool_size,
        max_overflow=database.max_overflow,
        pool_timeout=database.pool_timeout_seconds,
    )


def create_document_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Создаёт transaction-scoped AsyncSession factory."""
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
