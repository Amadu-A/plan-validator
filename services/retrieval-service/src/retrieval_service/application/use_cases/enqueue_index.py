# services/retrieval-service/src/retrieval_service/application/use_cases/enqueue_index.py

"""Use-case постановки normalized source reindex job в durable queue."""

from uuid import UUID, uuid4

from plan_validator_common.observability import log_execution_time

from retrieval_service.application.ports.index_job_publisher import IndexJobPublisher
from retrieval_service.application.ports.unit_of_work import RetrievalUnitOfWorkFactory
from retrieval_service.domain.exceptions import (
    RetrievalSourceConflictError,
    RetrievalSourceNotFoundError,
)
from retrieval_service.domain.source_index import (
    IndexSourceJob,
    NormalizedChunk,
    SourceIndexState,
    validate_chunks,
)


class EnqueueSourceIndexUseCase:
    """Проверяет Catalog registry identity до публикации expensive indexing job."""

    def __init__(
        self,
        *,
        uow_factory: RetrievalUnitOfWorkFactory,
        publisher: IndexJobPublisher,
        max_chunks: int,
        max_chunk_chars: int,
    ) -> None:
        """Сохраняет dependencies и bounded chunk policy."""
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._max_chunks = max_chunks
        self._max_chunk_chars = max_chunk_chars

    @log_execution_time("retrieval.enqueue_source_index")
    async def execute(
        self,
        *,
        source_id: UUID,
        source_sha256: str,
        chunks: tuple[NormalizedChunk, ...],
        correlation_id: str,
    ) -> UUID:
        """Validates source/chunks и durably enqueue'ит normalized index command."""
        validate_chunks(
            chunks,
            max_chunks=self._max_chunks,
            max_text_chars=self._max_chunk_chars,
        )

        async with self._uow_factory() as uow:
            source = await uow.source_indexes.get(source_id)

            if source is None:
                raise RetrievalSourceNotFoundError(
                    f"Managed source {source_id} is not registered in Retrieval"
                )

            if source.state is SourceIndexState.DELETED:
                raise RetrievalSourceConflictError(f"Managed source {source_id} is deleted")

            if source.source_sha256 != source_sha256:
                raise RetrievalSourceConflictError(
                    f"Source hash does not match Catalog registry for {source_id}"
                )

        job_id = uuid4()
        await self._publisher.publish(
            IndexSourceJob(
                job_id=job_id,
                source_id=source_id,
                source_sha256=source_sha256,
                chunks=chunks,
                correlation_id=correlation_id,
            )
        )

        return job_id
