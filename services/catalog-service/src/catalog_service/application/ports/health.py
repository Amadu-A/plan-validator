# services/catalog-service/src/catalog_service/application/ports/health.py

"""Application port readiness probe Catalog Service."""

from typing import Protocol


class DatabaseHealthProbe(Protocol):
    """Абстрагирует lightweight database readiness check."""

    async def is_ready(self) -> bool:
        """Возвращает True при доступности обязательной PostgreSQL dependency."""
