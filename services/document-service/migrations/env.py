# services/document-service/migrations/env.py

"""Alembic environment Document Service."""

import asyncio

import document_service.infrastructure.database.models  # noqa: F401
from alembic import context
from document_service.core.settings import load_document_settings
from document_service.infrastructure.database.base import Base
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

target_metadata = Base.metadata


def run_sync_migrations(connection: object) -> None:
    """Конфигурирует Alembic sync bridge."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        compare_type=True,
        version_table="document_alembic_version",
        version_table_schema="document",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Запускает migrations через temporary async engine."""
    settings = load_document_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_sync_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Document Service migrations require online mode")
asyncio.run(run_migrations_online())
