# services/context-service/src/context_service/infrastructure/messaging/rabbitmq.py

"""Shared RabbitMQ connection helper Context Service."""

from aio_pika import connect_robust
from aio_pika.abc import AbstractRobustConnection

from context_service.core.settings import ContextSettings


async def connect_context_broker(
    settings: ContextSettings,
) -> AbstractRobustConnection:
    """Создаёт robust AMQP connection с bounded heartbeat."""
    return await connect_robust(
        settings.broker_url,
        heartbeat=settings.context_broker.heartbeat_seconds,
    )
