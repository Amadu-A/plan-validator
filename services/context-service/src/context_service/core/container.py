# services/context-service/src/context_service/core/container.py

"""Composition root Context HTTP Service."""

from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncEngine

from context_service.application.use_cases.context_lifecycle import (
    CreateProjectContextUseCase,
    GetProjectContextUseCase,
    RegisterContextSourceUseCase,
    RequestProjectContextCleanupUseCase,
)
from context_service.application.use_cases.index_jobs import (
    EnqueueContextIndexUseCase,
)
from context_service.application.use_cases.runtime_status import (
    CheckContextReadinessUseCase,
    GetContextIndexJobUseCase,
)
from context_service.application.use_cases.search_context import (
    SearchProjectContextUseCase,
)
from context_service.core.settings import ContextSettings
from context_service.infrastructure.clock import SystemClock
from context_service.infrastructure.database.engine import (
    create_context_engine,
    create_context_session_factory,
)
from context_service.infrastructure.database.health import (
    SqlAlchemyDatabaseHealthProbe,
)
from context_service.infrastructure.database.uow import (
    SqlAlchemyContextUnitOfWorkFactory,
)
from context_service.infrastructure.messaging.embedding_gateway import (
    RabbitContextEmbeddingGateway,
)
from context_service.infrastructure.messaging.health import (
    RabbitBrokerHealthProbe,
)
from context_service.infrastructure.messaging.job_publisher import (
    RabbitContextIndexJobPublisher,
)
from context_service.infrastructure.vector_store.health import (
    QdrantHealthProbe,
)
from context_service.infrastructure.vector_store.qdrant import (
    QdrantContextVectorStore,
    build_qdrant_client,
)


@dataclass(slots=True)
class ContextContainer:
    """Хранит process-level dependencies Context HTTP Service."""

    settings: ContextSettings
    engine: AsyncEngine
    qdrant_client: AsyncQdrantClient

    create_context: CreateProjectContextUseCase
    get_context: GetProjectContextUseCase
    register_source: RegisterContextSourceUseCase
    request_cleanup: RequestProjectContextCleanupUseCase

    enqueue_index: EnqueueContextIndexUseCase
    get_index_job: GetContextIndexJobUseCase
    search_context: SearchProjectContextUseCase

    check_readiness: CheckContextReadinessUseCase

    async def aclose(self) -> None:
        """Освобождает PostgreSQL и Qdrant resources при shutdown."""
        await self.qdrant_client.close()
        await self.engine.dispose()


def build_container(
    settings: ContextSettings,
) -> ContextContainer:
    """Собирает Context adapters вокруг application use-cases."""
    engine = create_context_engine(settings)

    session_factory = create_context_session_factory(engine)

    uow_factory = SqlAlchemyContextUnitOfWorkFactory(session_factory)

    clock = SystemClock()

    qdrant = settings.context_qdrant

    qdrant_client = build_qdrant_client(
        host=qdrant.host,
        http_port=qdrant.http_port,
        grpc_port=qdrant.grpc_port,
        prefer_grpc=qdrant.prefer_grpc,
        timeout_seconds=qdrant.timeout_seconds,
    )

    vector_store = QdrantContextVectorStore(
        client=qdrant_client,
        collection_prefix=qdrant.collection_prefix,
        expected_vector_size=settings.context_embedding.vector_dimension,
    )

    embedding_gateway = RabbitContextEmbeddingGateway(settings)

    index_publisher = RabbitContextIndexJobPublisher(settings)

    return ContextContainer(
        settings=settings,
        engine=engine,
        qdrant_client=qdrant_client,
        create_context=CreateProjectContextUseCase(
            uow_factory=uow_factory,
            clock=clock,
            ttl_hours=settings.context_retention.grace_hours,
        ),
        get_context=GetProjectContextUseCase(uow_factory),
        register_source=RegisterContextSourceUseCase(
            uow_factory=uow_factory,
            clock=clock,
            ttl_hours=settings.context_retention.grace_hours,
        ),
        request_cleanup=RequestProjectContextCleanupUseCase(
            uow_factory=uow_factory,
            clock=clock,
        ),
        enqueue_index=EnqueueContextIndexUseCase(
            uow_factory=uow_factory,
            publisher=index_publisher,
            clock=clock,
            model_name=settings.context_embedding.model_name,
            vector_dimension=settings.context_embedding.vector_dimension,
            max_chunks=settings.context_indexing.max_chunks_per_source,
            max_chunk_chars=settings.context_indexing.max_chunk_chars,
            max_attempts=settings.context_queue.max_attempts,
            deadline_seconds=settings.context_queue.job_deadline_seconds,
        ),
        get_index_job=GetContextIndexJobUseCase(uow_factory),
        search_context=SearchProjectContextUseCase(
            uow_factory=uow_factory,
            embedding_gateway=embedding_gateway,
            vector_store=vector_store,
            expected_model=settings.context_embedding.model_name,
            expected_dimension=settings.context_embedding.vector_dimension,
            query_instruction=settings.context_embedding.query_instruction,
            default_limit=settings.context_search.default_limit,
            max_limit=settings.context_search.max_limit,
            default_score_threshold=(settings.context_search.default_score_threshold),
            max_query_chars=settings.context_search.max_query_chars,
        ),
        check_readiness=CheckContextReadinessUseCase(
            database=SqlAlchemyDatabaseHealthProbe(session_factory),
            vector_store=QdrantHealthProbe(qdrant_client),
            broker=RabbitBrokerHealthProbe(settings),
        ),
    )
