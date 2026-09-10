# services/catalog-service/src/catalog_service/application/ports/source_outbox_repository.py

"""Application port transactional outbox managed sources."""

from typing import Protocol

from catalog_service.domain.source import SourceOutboxMessage


class SourceOutboxRepository(Protocol):
    """Определяет Stage 7 persistence API durable outbox."""

    async def add(self, message: SourceOutboxMessage) -> None:
        """Добавляет outbox message в текущую database transaction."""
