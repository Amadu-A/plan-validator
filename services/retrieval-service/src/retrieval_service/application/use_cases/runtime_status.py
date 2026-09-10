# services/retrieval-service/src/retrieval_service/application/use_cases/runtime_status.py

"""Operational use-cases Retrieval Service."""

from uuid import UUID

from retrieval_service.application.ports.health import HealthProbe
from retrieval_service.application.ports.unit_of_work import RetrievalUnitOfWorkFactory
from retrieval_service.application.ports.vector_store import ManagedSourceVectorStore
from retrieval_service.domain.exceptions import RetrievalSourceNotFoundError
from retrieval_service.domain.source_index import ManagedSourceIndex


class CheckReadinessUseCase:
    """Проверяет PostgreSQL, Qdrant alias и RabbitMQ без mutation."""

    def __init__(
        self,
        *,
        database: HealthProbe,
        vector_store: ManagedSourceVectorStore,
        broker: HealthProbe,
    ) -> None:
        """Сохраняет mandatory dependency probes."""
        self._database = database
        self._vector_store = vector_store
        self._broker = broker

    async def execute(self) -> bool:
        """Возвращает True только когда все mandatory dependencies готовы."""
        return (
            await self._database.ready()
            and await self._vector_store.ready()
            and await self._broker.ready()
        )


class GetSourceIndexStatusUseCase:
    """Возвращает Retrieval-owned source indexing lifecycle."""

    def __init__(self, uow_factory: RetrievalUnitOfWorkFactory) -> None:
        """Сохраняет Retrieval UoW factory."""
        self._uow_factory = uow_factory

    async def execute(self, source_id: UUID) -> ManagedSourceIndex:
        """Возвращает source status либо domain not-found error."""
        async with self._uow_factory() as uow:
            source = await uow.source_indexes.get(source_id)

        if source is None:
            raise RetrievalSourceNotFoundError(f"Managed source {source_id} is not registered")

        return source
