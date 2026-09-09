# services/auth-service/src/auth_service/application/use_cases/check_readiness.py

"""Lightweight readiness use-case Authentication Service."""

from auth_service.application.ports.health import (
    DatabaseHealthProbe,
)


class CheckReadinessUseCase:
    """Проверяет только обязательную PostgreSQL dependency."""

    def __init__(
        self,
        database_probe: DatabaseHealthProbe,
    ) -> None:
        """Сохраняет database health port."""
        self._database_probe = database_probe

    async def execute(self) -> bool:
        """Возвращает operational readiness без тяжёлой работы."""
        return await self._database_probe.is_ready()
