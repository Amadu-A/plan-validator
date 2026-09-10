# services/retrieval-service/src/retrieval_service/infrastructure/messaging/rabbitmq.py

"""Shared RabbitMQ connection helpers Retrieval processes."""

from aio_pika import connect_robust
from aio_pika.abc import AbstractRobustConnection

from retrieval_service.core.settings import RetrievalSettings


async def connect_retrieval_broker(settings: RetrievalSettings) -> AbstractRobustConnection:
    """Создаёт robust AMQP connection с configured heartbeat."""
    return await connect_robust(
        settings.broker_url,
        heartbeat=settings.retrieval_broker.heartbeat_seconds,
    )
