# services/retrieval-service/src/retrieval_service/core/container.py

"""Composition root Retrieval HTTP Service."""

from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncEngine

from retrieval_service.application.use_cases.enqueue_index import EnqueueSourceIndexUseCase
from retrieval_service.application.use_cases.runtime_status import (
    CheckReadinessUseCase,
    GetSourceIndexStatusUseCase,
)
from retrieval_service.application.use_cases.search_sources import SearchManagedSourcesUseCase
from retrieval_service.core.settings import RetrievalSettings
from retrieval_service.infrastructure.database.engine import (
    create_retrieval_engine,
    create_retrieval_session_factory,
)
from retrieval_service.infrastructure.database.health import SqlAlchemyDatabaseHealthProbe
from retrieval_service.infrastructure.database.uow import SqlAlchemyRetrievalUnitOfWorkFactory
from retrieval_service.infrastructure.messaging.embedding_gateway import RabbitEmbeddingGateway
from retrieval_service.infrastructure.messaging.health import RabbitBrokerHealthProbe
from retrieval_service.infrastructure.messaging.index_job_publisher import RabbitIndexJobPublisher
from retrieval_service.infrastructure.vector_store.qdrant import (
    QdrantManagedSourceVectorStore,
    build_qdrant_client,
)


@dataclass(slots=True)
class RetrievalContainer:
    """Хранит process-level dependencies Retrieval HTTP Service."""

    settings: RetrievalSettings
    engine: AsyncEngine
    qdrant_client: AsyncQdrantClient
    enqueue_source_index: EnqueueSourceIndexUseCase
    search_sources: SearchManagedSourcesUseCase
    get_source_status: GetSourceIndexStatusUseCase
    check_readiness: CheckReadinessUseCase

    async def aclose(self) -> None:
        """Освобождает PostgreSQL и Qdrant connections при shutdown."""
        await self.qdrant_client.close()
        await self.engine.dispose()


def build_container(settings: RetrievalSettings) -> RetrievalContainer:
    """Собирает concrete Retrieval adapters вокруг application use-cases."""
    engine = create_retrieval_engine(settings)
    session_factory = create_retrieval_session_factory(engine)
    uow_factory = SqlAlchemyRetrievalUnitOfWorkFactory(session_factory)
    qdrant = settings.retrieval_qdrant
    qdrant_client = build_qdrant_client(
        host=qdrant.host,
        http_port=qdrant.http_port,
        grpc_port=qdrant.grpc_port,
        prefer_grpc=qdrant.prefer_grpc,
        timeout_seconds=qdrant.timeout_seconds,
    )
    vector_store = QdrantManagedSourceVectorStore(
        client=qdrant_client,
        alias_name=qdrant.alias_name,
        expected_vector_size=qdrant.vector_size,
    )
    embedding_gateway = RabbitEmbeddingGateway(settings)
    index_publisher = RabbitIndexJobPublisher(settings)

    return RetrievalContainer(
        settings=settings,
        engine=engine,
        qdrant_client=qdrant_client,
        enqueue_source_index=EnqueueSourceIndexUseCase(
            uow_factory=uow_factory,
            publisher=index_publisher,
            max_chunks=settings.retrieval_indexing.max_chunks_per_source,
            max_chunk_chars=settings.retrieval_indexing.max_chunk_chars,
        ),
        search_sources=SearchManagedSourcesUseCase(
            uow_factory=uow_factory,
            embedding_gateway=embedding_gateway,
            vector_store=vector_store,
            expected_model=settings.retrieval_embedding.model_name,
            expected_dimension=settings.retrieval_embedding.vector_dimension,
            max_limit=settings.retrieval_search.max_limit,
        ),
        get_source_status=GetSourceIndexStatusUseCase(uow_factory),
        check_readiness=CheckReadinessUseCase(
            database=SqlAlchemyDatabaseHealthProbe(session_factory),
            vector_store=vector_store,
            broker=RabbitBrokerHealthProbe(settings),
        ),
    )
