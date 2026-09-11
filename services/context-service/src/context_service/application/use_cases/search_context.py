# services/context-service/src/context_service/application/use_cases/search_context.py

"""Typed T/PZ retrieval use-case без normative semantics."""

from plan_validator_common.observability import log_execution_time

from context_service.application.ports.embedding_gateway import ContextEmbeddingGateway
from context_service.application.ports.unit_of_work import ContextUnitOfWorkFactory
from context_service.application.ports.vector_store import ContextVectorStore
from context_service.domain.exceptions import ContextEmbeddingError, ContextValidationError
from context_service.domain.models import ContextSourceState, ProjectContextState
from context_service.domain.search import ContextSearchHit, ContextSearchQuery


class SearchProjectContextUseCase:
    """Ищет только в active T/PZ generation указанного владельца/context."""

    def __init__(
        self,
        *,
        uow_factory: ContextUnitOfWorkFactory,
        embedding_gateway: ContextEmbeddingGateway,
        vector_store: ContextVectorStore,
        expected_model: str,
        expected_dimension: int,
        query_instruction: str,
        default_limit: int,
        max_limit: int,
        default_score_threshold: float,
        max_query_chars: int,
    ) -> None:
        """Сохраняет typed retrieval dependencies и bounded defaults."""
        self._uow_factory = uow_factory
        self._embedding_gateway = embedding_gateway
        self._vector_store = vector_store
        self._expected_model = expected_model
        self._expected_dimension = expected_dimension
        self._query_instruction = query_instruction
        self._default_limit = default_limit
        self._max_limit = max_limit
        self._default_score_threshold = default_score_threshold
        self._max_query_chars = max_query_chars

    @log_execution_time("context.search_project_context")
    async def execute(
        self,
        query: ContextSearchQuery,
        *,
        correlation_id: str,
    ) -> tuple[ContextSearchHit, ...]:
        """Возвращает hits только active source/fingerprint либо пустой результат."""
        text = query.text.strip()
        if not text:
            raise ContextValidationError("Context search text must not be empty")
        if len(text) > self._max_query_chars:
            raise ContextValidationError(
                f"Context search text must not exceed {self._max_query_chars} characters"
            )

        limit = query.limit if query.limit is not None else self._default_limit
        if limit < 1 or limit > self._max_limit:
            raise ContextValidationError(
                f"Context search limit must be between 1 and {self._max_limit}"
            )

        async with self._uow_factory() as uow:
            context = await uow.contexts.get_for_user(
                user_id=query.user_id,
                context_id=query.context_id,
            )
            source = await uow.sources.get_for_context_kind(
                user_id=query.user_id,
                context_id=query.context_id,
                kind=query.kind,
            )

        if context is None or context.state is not ProjectContextState.ACTIVE:
            return ()
        if source is None or source.state is not ContextSourceState.INDEXED:
            return ()
        if source.active_fingerprint is None:
            return ()

        embedded = await self._embedding_gateway.embed_texts(
            texts=(text,),
            instruction=self._query_instruction,
            correlation_id=correlation_id,
        )
        if embedded.model != self._expected_model:
            raise ContextEmbeddingError(
                f"Embedding model mismatch: expected {self._expected_model}, got {embedded.model}"
            )
        if embedded.dimension != self._expected_dimension:
            raise ContextEmbeddingError("Embedding dimension mismatch for Context search")
        if len(embedded.vectors) != 1:
            raise ContextEmbeddingError("Context search embedding must return one vector")

        score_threshold = (
            query.score_threshold
            if query.score_threshold is not None
            else self._default_score_threshold
        )
        if score_threshold < -1.0 or score_threshold > 1.0:
            raise ContextValidationError("Context search score_threshold must be between -1 and 1")

        normalized_query = ContextSearchQuery(
            user_id=query.user_id,
            context_id=query.context_id,
            kind=query.kind,
            text=text,
            limit=limit,
            score_threshold=score_threshold,
        )
        return await self._vector_store.search(
            query=normalized_query,
            source=source,
            query_vector=embedded.vectors[0],
        )
