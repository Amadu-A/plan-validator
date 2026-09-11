# services/catalog-service/src/catalog_service/infrastructure/database/repositories/source_outbox.py

"""SQLAlchemy implementation SourceOutboxRepository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from catalog_service.domain.source import SourceOutboxMessage
from catalog_service.infrastructure.database.models.source_outbox import (
    SourceOutboxMessageModel,
)


class SqlAlchemySourceOutboxRepository:
    """Persist'ит и блокирует durable source events Catalog schema."""

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

    async def get_next_pending_for_update(self) -> SourceOutboxMessage | None:
        """Блокирует oldest unpublished row с SKIP LOCKED."""
        statement = (
            select(SourceOutboxMessageModel)
            .where(SourceOutboxMessageModel.published_at.is_(None))
            .order_by(
                SourceOutboxMessageModel.attempt_count,
                SourceOutboxMessageModel.created_at,
                SourceOutboxMessageModel.id,
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        model = await self._session.scalar(statement)

        if model is None:
            return None

        return self._to_domain(model)

    async def mark_published(self, *, message_id: UUID, published_at: datetime) -> None:
        """Фиксирует publisher-confirmed delivery."""
        statement = (
            update(SourceOutboxMessageModel)
            .where(SourceOutboxMessageModel.id == message_id)
            .values(
                published_at=published_at,
                last_error=None,
            )
        )
        await self._session.execute(statement)
        await self._session.flush()

    async def mark_failed(self, *, message_id: UUID, error_message: str) -> None:
        """Фиксирует failed attempt без потери durable outbox row."""
        statement = (
            update(SourceOutboxMessageModel)
            .where(SourceOutboxMessageModel.id == message_id)
            .values(
                attempt_count=SourceOutboxMessageModel.attempt_count + 1,
                last_error=error_message[:2000],
            )
        )
        await self._session.execute(statement)
        await self._session.flush()

    @staticmethod
    def _to_domain(model: SourceOutboxMessageModel) -> SourceOutboxMessage:
        """Преобразует persistence model в immutable domain event."""
        payload = {
            str(key): value if isinstance(value, (str, int)) or value is None else str(value)
            for key, value in model.payload.items()
        }

        return SourceOutboxMessage(
            id=model.id,
            source_id=model.source_id,
            event_type=model.event_type,
            payload=payload,
            created_at=model.created_at,
            published_at=model.published_at,
            attempt_count=model.attempt_count,
            last_error=model.last_error,
        )
