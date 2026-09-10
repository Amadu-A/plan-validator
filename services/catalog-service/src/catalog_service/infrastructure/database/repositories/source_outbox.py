# services/catalog-service/src/catalog_service/infrastructure/database/repositories/source_outbox.py

"""SQLAlchemy implementation SourceOutboxRepository."""

from sqlalchemy.ext.asyncio import AsyncSession

from catalog_service.domain.source import SourceOutboxMessage
from catalog_service.infrastructure.database.models.source_outbox import (
    SourceOutboxMessageModel,
)


class SqlAlchemySourceOutboxRepository:
    """Persist'ит durable source events без RabbitMQ coupling."""

    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет transaction-scoped AsyncSession."""
        self._session = session

    async def add(self, message: SourceOutboxMessage) -> None:
        """Добавляет outbox message в текущую transaction."""
        self._session.add(
            SourceOutboxMessageModel(
                id=message.id,
                source_id=message.source_id,
                event_type=message.event_type,
                payload=dict(message.payload),
                created_at=message.created_at,
                published_at=message.published_at,
                attempt_count=message.attempt_count,
                last_error=message.last_error,
            )
        )

        await self._session.flush()
