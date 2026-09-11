# services/catalog-service/src/catalog_service/application/ports/source_outbox_repository.py

"""Application port transactional outbox managed sources."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from catalog_service.domain.source import SourceOutboxMessage


class SourceOutboxRepository(Protocol):
    """Определяет persistence API durable source outbox."""

    async def add(self, message: SourceOutboxMessage) -> None:
        """Добавляет outbox message в текущую database transaction."""

    async def get_next_pending_for_update(self) -> SourceOutboxMessage | None:
        """Блокирует и возвращает старейшее unpublished сообщение."""

    async def mark_published(self, *, message_id: UUID, published_at: datetime) -> None:
        """Фиксирует подтверждённую публикацию сообщения."""

    async def mark_failed(self, *, message_id: UUID, error_message: str) -> None:
        """Увеличивает счётчик попыток и сохраняет безопасную ошибку."""
