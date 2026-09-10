# services/retrieval-service/migrations/env.py

"""Alembic environment Retrieval Service."""

import asyncio

import retrieval_service.infrastructure.database.models  # noqa: F401
from alembic import context
from retrieval_service.core.settings import load_retrieval_settings
from retrieval_service.infrastructure.database.base import Base
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

target_metadata = Base.metadata


def run_sync_migrations(connection: object) -> None:
    """Конфигурирует Alembic context для sync bridge."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        compare_type=True,
        version_table="retrieval_alembic_version",
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Запускает migrations через temporary async engine."""
    settings = load_retrieval_settings()
    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
    )

    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_sync_migrations)
    finally:
        await engine.dispose()


def run_migrations_offline() -> None:
    """Генерирует migration SQL без database connection."""
    settings = load_retrieval_settings()
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        include_schemas=True,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="retrieval_alembic_version",
    )

    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
