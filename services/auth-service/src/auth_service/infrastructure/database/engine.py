# services/auth-service/src/auth_service/infrastructure/database/engine.py

"""Async SQLAlchemy engine/session factory Authentication Service."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from auth_service.core.settings import (
    AuthSettings,
)


def create_auth_engine(
    settings: AuthSettings,
) -> AsyncEngine:
    """Создаёт bounded async SQLAlchemy connection pool."""
    return create_async_engine(
        settings.database_url,
        pool_size=(settings.auth_database.pool_size),
        max_overflow=(settings.auth_database.max_overflow),
        pool_timeout=(settings.auth_database.pool_timeout_seconds),
        pool_pre_ping=True,
    )


def create_auth_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Создаёт transaction-scoped AsyncSession factory."""
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )
