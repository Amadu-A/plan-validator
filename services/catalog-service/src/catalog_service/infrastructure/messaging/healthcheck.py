# services/catalog-service/src/catalog_service/infrastructure/messaging/healthcheck.py

"""Container healthcheck Catalog transactional outbox dispatcher."""

import asyncio

from aio_pika import ExchangeType, connect_robust

from catalog_service.core.settings import load_catalog_outbox_settings
from catalog_service.infrastructure.database.engine import (
    create_catalog_engine,
    create_catalog_session_factory,
)
from catalog_service.infrastructure.database.health import SqlAlchemyDatabaseHealthProbe


async def check() -> None:
    """Проверяет Catalog PostgreSQL и shared RabbitMQ exchange без публикации event."""
    settings = load_catalog_outbox_settings()
    engine = create_catalog_engine(settings)
    session_factory = create_catalog_session_factory(engine)
    database_probe = SqlAlchemyDatabaseHealthProbe(session_factory)

    try:
        if not await database_probe.is_ready():
            raise RuntimeError("Catalog PostgreSQL is not ready")

        connection = await connect_robust(
            settings.broker_url,
            heartbeat=settings.catalog_broker.heartbeat_seconds,
        )
        async with connection:
            channel = await connection.channel()
            await channel.declare_exchange(
                settings.catalog_outbox.exchange_name,
                ExchangeType.TOPIC,
                passive=True,
            )
    finally:
        await engine.dispose()


def main() -> None:
    """Запускает async dispatcher healthcheck как one-shot process."""
    asyncio.run(check())


if __name__ == "__main__":
    main()
