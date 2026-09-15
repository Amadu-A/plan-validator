# services/context-service/src/context_service/application/ports/health.py

"""Application port lightweight readiness probe Context Service."""

from typing import Protocol


class HealthProbe(Protocol):
    """Проверяет доступность одной mandatory runtime dependency."""

    async def ready(self) -> bool:
        """Возвращает True, когда dependency готова обслуживать Context runtime."""
        ...
