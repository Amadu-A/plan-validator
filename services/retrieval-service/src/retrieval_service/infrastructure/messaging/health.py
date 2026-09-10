# services/retrieval-service/src/retrieval_service/infrastructure/messaging/health.py

"""RabbitMQ health probe Retrieval Service."""

from retrieval_service.core.settings import RetrievalSettings
from retrieval_service.infrastructure.messaging.rabbitmq import connect_retrieval_broker


class RabbitBrokerHealthProbe:
    """Проверяет broker и существование mandatory embedding/index queues."""

    def __init__(self, settings: RetrievalSettings) -> None:
        """Сохраняет broker/queue settings."""
        self._settings = settings

    async def ready(self) -> bool:
        """Возвращает True при доступном broker и mandatory queues."""
        try:
            connection = await connect_retrieval_broker(self._settings)

            async with connection:
                channel = await connection.channel()
                await channel.declare_queue(
                    self._settings.retrieval_queues.embedding_queue_name,
                    passive=True,
                )
                await channel.declare_queue(
                    self._settings.retrieval_queues.index_queue_name,
                    passive=True,
                )
            return True
        except Exception:
            return False
