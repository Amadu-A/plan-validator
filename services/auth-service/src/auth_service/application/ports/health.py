# services/auth-service/src/auth_service/application/ports/health.py

"""Application port readiness dependency Authentication Service."""

from typing import Protocol


class DatabaseHealthProbe(Protocol):
    """Проверяет минимальную доступность обязательной database dependency."""

    async def is_ready(self) -> bool:
        """Возвращает True при успешном lightweight database probe."""
