# services/context-service/src/context_service/infrastructure/messaging/health.py

"""RabbitMQ health probe Context Service."""

from context_service.core.settings import ContextSettings
from context_service.infrastructure.messaging.rabbitmq import (
    connect_context_broker,
)


class RabbitBrokerHealthProbe:
    """Проверяет broker и mandatory Context/Embedding queues."""

    def __init__(
        self,
        settings: ContextSettings,
    ) -> None:
        """Сохраняет broker/queue settings."""
        self._settings = settings

    async def ready(self) -> bool:
        """Возвращает True при доступном broker и mandatory queues."""
        try:
            connection = await connect_context_broker(self._settings)

            async with connection:
                channel = await connection.channel()

                await channel.declare_queue(
                    self._settings.context_queue.index_queue_name,
                    passive=True,
                )

                await channel.declare_queue(
                    self._settings.context_embedding.queue_name,
                    passive=True,
                )

        except Exception:
            return False

        return True
