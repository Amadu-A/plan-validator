# services/catalog-service/src/catalog_service/application/ports/source_event_publisher.py

"""Application port публикации Catalog source lifecycle events."""

from typing import Protocol

from catalog_service.domain.source import SourceOutboxMessage


class SourceEventPublishError(RuntimeError):
    """Публикация durable source event во внешнюю шину не подтверждена."""


class SourceEventPublisher(Protocol):
    """Публикует одно durable source lifecycle event."""

    async def publish(self, message: SourceOutboxMessage) -> None:
        """Публикует сообщение или поднимает SourceEventPublishError."""
