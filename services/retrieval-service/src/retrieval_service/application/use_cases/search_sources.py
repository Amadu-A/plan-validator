# services/retrieval-service/src/retrieval_service/application/use_cases/search_sources.py

"""Use-case typed N/U retrieval через embedding queue и Qdrant."""

from plan_validator_common.observability import log_execution_time

from retrieval_service.application.ports.embedding_gateway import EmbeddingGateway
from retrieval_service.application.ports.unit_of_work import RetrievalUnitOfWorkFactory
from retrieval_service.application.ports.vector_store import ManagedSourceVectorStore
from retrieval_service.domain.exceptions import RetrievalEmbeddingError
from retrieval_service.domain.search import SearchHit, SearchQuery

_QUERY_INSTRUCTION = (
    "Represent this query for retrieving the most relevant construction document fragments."
)


class SearchManagedSourcesUseCase:
    """Гарантирует tenant + N/U + active fingerprint isolation до Qdrant search."""

    def __init__(
        self,
        *,
        uow_factory: RetrievalUnitOfWorkFactory,
        embedding_gateway: EmbeddingGateway,
        vector_store: ManagedSourceVectorStore,
        expected_model: str,
        expected_dimension: int,
        max_limit: int,
    ) -> None:
        """Сохраняет retrieval dependencies и model compatibility contract."""
        self._uow_factory = uow_factory
        self._embedding_gateway = embedding_gateway
        self._vector_store = vector_store
        self._expected_model = expected_model
        self._expected_dimension = expected_dimension
        self._max_limit = max_limit

    @log_execution_time("retrieval.search_managed_sources")
    async def execute(self, query: SearchQuery, *, correlation_id: str) -> tuple[SearchHit, ...]:
        """Выполняет typed search только по DB-active source generations."""
        query.validate(max_limit=self._max_limit)

        async with self._uow_factory() as uow:
            active_version_keys = await uow.source_indexes.list_active_version_keys(
                user_id=query.user_id,
                kind=query.kind,
                section_ids=query.section_ids,
                source_ids=query.source_ids,
            )

        if not active_version_keys:
            return ()

        embedded = await self._embedding_gateway.embed_texts(
            texts=(query.text,),
            instruction=_QUERY_INSTRUCTION,
            correlation_id=correlation_id,
        )

        if embedded.model != self._expected_model:
            raise RetrievalEmbeddingError(
                f"Embedding model mismatch: expected {self._expected_model}, got {embedded.model}"
            )

        if embedded.dimension != self._expected_dimension or len(embedded.vectors) != 1:
            raise RetrievalEmbeddingError("Invalid query embedding response")

        return await self._vector_store.search(
            query=query,
            query_vector=embedded.vectors[0],
            active_version_keys=active_version_keys,
        )
