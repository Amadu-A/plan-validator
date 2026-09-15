# services/context-service/src/context_service/application/use_cases/runtime_status.py

"""Operational status use-cases Context Service."""

from uuid import UUID

from context_service.application.ports.health import HealthProbe
from context_service.application.ports.unit_of_work import ContextUnitOfWorkFactory
from context_service.domain.exceptions import ContextIndexJobNotFoundError
from context_service.domain.models import ContextIndexJob


class CheckContextReadinessUseCase:
    """Проверяет обязательные Context runtime dependencies."""

    def __init__(
        self,
        *,
        database: HealthProbe,
        vector_store: HealthProbe,
        broker: HealthProbe,
    ) -> None:
        """Сохраняет lightweight probes без infrastructure dependency."""
        self._database = database
        self._vector_store = vector_store
        self._broker = broker

    async def execute(self) -> bool:
        """Возвращает True, только когда все mandatory dependencies готовы."""
        database_ready = await self._database.ready()
        vector_store_ready = await self._vector_store.ready()
        broker_ready = await self._broker.ready()

        return database_ready and vector_store_ready and broker_ready


class GetContextIndexJobUseCase:
    """Возвращает durable indexing job только внутри owner/context scope."""

    def __init__(
        self,
        uow_factory: ContextUnitOfWorkFactory,
    ) -> None:
        """Сохраняет transaction-scoped Unit of Work factory."""
        self._uow_factory = uow_factory

    async def execute(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
        job_id: UUID,
    ) -> ContextIndexJob:
        """Возвращает job либо owner-safe not-found error."""
        async with self._uow_factory() as uow:
            job = await uow.jobs.get(job_id)

        if job is None or job.user_id != user_id or job.context_id != context_id:
            raise ContextIndexJobNotFoundError("Context indexing job was not found")

        return job
