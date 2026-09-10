# services/retrieval-service/src/retrieval_service/application/ports/health.py

"""Application health probe contracts Retrieval Service."""

from typing import Protocol


class HealthProbe(Protocol):
    """Проверяет доступность одной обязательной dependency."""

    async def ready(self) -> bool:
        """Возвращает True при доступной dependency."""
