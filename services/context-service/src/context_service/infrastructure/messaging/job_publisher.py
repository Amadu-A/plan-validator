# services/context-service/src/context_service/infrastructure/messaging/job_publisher.py

"""RabbitMQ publisher persistent Context indexing job identifiers."""

from datetime import timedelta
from uuid import UUID

from aio_pika import DeliveryMode, Message

from context_service.application.ports.job_publisher import ContextIndexJobPublisher
from context_service.core.settings import ContextSettings
from context_service.domain.exceptions import ContextJobPublishError
from context_service.infrastructure.messaging.rabbitmq import connect_context_broker
from context_service.infrastructure.messaging.schemas import ContextIndexJobMessage


class RabbitContextIndexJobPublisher(ContextIndexJobPublisher):
    """Публикует только job_id; chunks и state остаются в PostgreSQL."""

    def __init__(self, settings: ContextSettings) -> None:
        """Сохраняет immutable broker/queue settings."""
        self._settings = settings

    async def publish(
        self,
        *,
        job_id: UUID,
        correlation_id: str,
    ) -> None:
        """Публикует persistent command с per-message TTL как второй защитой."""
        payload = ContextIndexJobMessage(
            job_id=job_id,
            correlation_id=correlation_id,
        )
        connection = None

        try:
            connection = await connect_context_broker(self._settings)
            channel = await connection.channel(
                publisher_confirms=True,
                on_return_raises=True,
            )
            await channel.declare_queue(
                self._settings.context_queue.index_queue_name,
                passive=True,
            )
            await channel.default_exchange.publish(
                Message(
                    body=payload.model_dump_json().encode("utf-8"),
                    content_type="application/json",
                    content_encoding="utf-8",
                    message_id=str(job_id),
                    correlation_id=correlation_id,
                    delivery_mode=DeliveryMode.PERSISTENT,
                    expiration=timedelta(milliseconds=self._settings.context_queue.message_ttl_ms),
                ),
                routing_key=self._settings.context_queue.index_queue_name,
                mandatory=True,
            )
        except ContextJobPublishError:
            raise
        except Exception as exc:
            raise ContextJobPublishError("Failed to enqueue Context indexing job") from exc
        finally:
            if connection is not None:
                await connection.close()
