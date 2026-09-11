# services/catalog-service/src/catalog_service/infrastructure/messaging/source_event_publisher.py

"""RabbitMQ publisher Catalog source lifecycle events."""

import json

from aio_pika import DeliveryMode, ExchangeType, Message, connect_robust
from aio_pika.abc import AbstractExchange, AbstractRobustConnection

from catalog_service.application.ports.source_event_publisher import SourceEventPublishError
from catalog_service.core.settings import CatalogOutboxProcessSettings
from catalog_service.domain.source import SourceOutboxMessage


class RabbitSourceEventPublisher:
    """Публикует durable topic events с publisher confirms и mandatory routing."""

    def __init__(
        self,
        *,
        connection: AbstractRobustConnection,
        exchange: AbstractExchange,
    ) -> None:
        """Сохраняет confirmed RabbitMQ connection/exchange."""
        self._connection = connection
        self._exchange = exchange

    @classmethod
    async def create(
        cls,
        settings: CatalogOutboxProcessSettings,
    ) -> "RabbitSourceEventPublisher":
        """Создаёт robust publisher и durable topic exchange."""
        connection = await connect_robust(
            settings.broker_url,
            heartbeat=settings.catalog_broker.heartbeat_seconds,
        )
        channel = await connection.channel(
            publisher_confirms=True,
            on_return_raises=True,
        )
        exchange = await channel.declare_exchange(
            settings.catalog_outbox.exchange_name,
            ExchangeType.TOPIC,
            durable=True,
            auto_delete=False,
        )

        return cls(connection=connection, exchange=exchange)

    async def publish(self, message: SourceOutboxMessage) -> None:
        """Публикует storage-neutral source event или поднимает safe port error."""
        envelope = {
            "schema_version": 1,
            "event_id": str(message.id),
            "event_type": message.event_type,
            "occurred_at": message.created_at.isoformat(),
            "source": dict(message.payload),
        }

        try:
            await self._exchange.publish(
                Message(
                    body=json.dumps(
                        envelope,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8"),
                    content_type="application/json",
                    content_encoding="utf-8",
                    delivery_mode=DeliveryMode.PERSISTENT,
                    message_id=str(message.id),
                    correlation_id=str(message.source_id),
                    type=message.event_type,
                ),
                routing_key=message.event_type,
                mandatory=True,
            )
        except Exception as exc:
            raise SourceEventPublishError(
                f"RabbitMQ did not confirm source event {message.id}"
            ) from exc

    async def aclose(self) -> None:
        """Закрывает robust AMQP connection dispatcher."""
        await self._connection.close()
