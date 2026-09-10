# services/catalog-service/src/catalog_service/application/use_cases/check_readiness.py

"""Readiness use-case Catalog Service."""

from catalog_service.application.ports.health import DatabaseHealthProbe


class CheckReadinessUseCase:
    """Проверяет обязательную PostgreSQL dependency."""

    def __init__(self, database_probe: DatabaseHealthProbe) -> None:
        """Сохраняет database health port."""
        self._database_probe = database_probe

    async def execute(self) -> bool:
        """Возвращает текущую database readiness."""
        return await self._database_probe.is_ready()
