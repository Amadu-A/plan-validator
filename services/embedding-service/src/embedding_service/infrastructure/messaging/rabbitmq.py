# services/embedding-service/src/embedding_service/infrastructure/messaging/rabbitmq.py

"""Shared RabbitMQ connection helpers Embedding worker/client."""

from aio_pika import connect_robust
from aio_pika.abc import AbstractRobustConnection

from embedding_service.core.settings import EmbeddingWorkerSettings


async def connect_embedding_broker(
    settings: EmbeddingWorkerSettings,
) -> AbstractRobustConnection:
    """Создаёт robust AMQP connection с configured heartbeat."""
    return await connect_robust(
        settings.broker_url,
        heartbeat=settings.embedding_broker.heartbeat_seconds,
    )
