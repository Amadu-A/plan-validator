# services/retrieval-service/src/retrieval_service/infrastructure/messaging/healthcheck.py

"""Container healthcheck Retrieval background worker prerequisites."""

import asyncio

from retrieval_service.core.settings import load_retrieval_worker_settings
from retrieval_service.infrastructure.database.engine import (
    create_retrieval_engine,
    create_retrieval_session_factory,
)
from retrieval_service.infrastructure.database.health import SqlAlchemyDatabaseHealthProbe
from retrieval_service.infrastructure.messaging.rabbitmq import connect_retrieval_broker
from retrieval_service.infrastructure.vector_store.qdrant import (
    QdrantManagedSourceVectorStore,
    build_qdrant_client,
)


async def check() -> None:
    """Проверяет PostgreSQL, Qdrant alias и все mandatory RabbitMQ queues."""
    settings = load_retrieval_worker_settings()
    engine = create_retrieval_engine(settings)
    session_factory = create_retrieval_session_factory(engine)
    database_probe = SqlAlchemyDatabaseHealthProbe(session_factory)
    qdrant = settings.retrieval_qdrant
    client = build_qdrant_client(
        host=qdrant.host,
        http_port=qdrant.http_port,
        grpc_port=qdrant.grpc_port,
        prefer_grpc=qdrant.prefer_grpc,
        timeout_seconds=qdrant.timeout_seconds,
    )
    vector_store = QdrantManagedSourceVectorStore(
        client=client,
        alias_name=qdrant.alias_name,
        expected_vector_size=qdrant.vector_size,
    )

    try:
        if not await database_probe.ready():
            raise RuntimeError("Retrieval PostgreSQL is not ready")

        if not await vector_store.ready():
            raise RuntimeError("Retrieval Qdrant alias is not ready")

        connection = await connect_retrieval_broker(settings)

        async with connection:
            channel = await connection.channel()

            for queue_name in (
                settings.retrieval_queues.embedding_queue_name,
                settings.retrieval_queues.catalog_queue_name,
                settings.retrieval_queues.index_queue_name,
            ):
                await channel.declare_queue(queue_name, passive=True)
    finally:
        await client.close()
        await engine.dispose()


def main() -> None:
    """Запускает async worker healthcheck как one-shot process."""
    asyncio.run(check())


if __name__ == "__main__":
    main()
