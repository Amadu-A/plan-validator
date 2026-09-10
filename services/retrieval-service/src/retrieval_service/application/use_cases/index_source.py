# services/retrieval-service/src/retrieval_service/application/use_cases/index_source.py

"""Use-case crash-safe N/U source reindex lifecycle."""

from plan_validator_common.observability import log_execution_time

from retrieval_service.application.ports.clock import Clock
from retrieval_service.application.ports.embedding_gateway import EmbeddingGateway
from retrieval_service.application.ports.unit_of_work import RetrievalUnitOfWorkFactory
from retrieval_service.application.ports.vector_store import ManagedSourceVectorStore
from retrieval_service.domain.exceptions import (
    RetrievalEmbeddingError,
    RetrievalSourceConflictError,
    RetrievalSourceNotFoundError,
)
from retrieval_service.domain.source_index import (
    IndexSourceJob,
    ManagedSourceIndex,
    SourceIndexResult,
    SourceIndexState,
    calculate_index_fingerprint,
    validate_chunks,
)

_INDEX_INSTRUCTION = (
    "Represent this construction document fragment for retrieval of relevant "
    "project requirements and normative evidence."
)


class IndexManagedSourceUseCase:
    """Пишет candidate vectors, переключает fingerprint и чистит stale data."""

    def __init__(
        self,
        *,
        uow_factory: RetrievalUnitOfWorkFactory,
        embedding_gateway: EmbeddingGateway,
        vector_store: ManagedSourceVectorStore,
        clock: Clock,
        expected_model: str,
        expected_dimension: int,
        max_chunks: int,
        max_chunk_chars: int,
    ) -> None:
        """Сохраняет indexing dependencies и model compatibility contract."""
        self._uow_factory = uow_factory
        self._embedding_gateway = embedding_gateway
        self._vector_store = vector_store
        self._clock = clock
        self._expected_model = expected_model
        self._expected_dimension = expected_dimension
        self._max_chunks = max_chunks
        self._max_chunk_chars = max_chunk_chars

    @log_execution_time("retrieval.index_managed_source")
    async def execute(self, job: IndexSourceJob) -> SourceIndexResult:
        """Выполняет idempotent candidate→activate→cleanup reindex sequence."""
        validate_chunks(
            job.chunks,
            max_chunks=self._max_chunks,
            max_text_chars=self._max_chunk_chars,
        )

        async with self._uow_factory() as uow:
            source = await uow.source_indexes.get(job.source_id)

        if source is None:
            raise RetrievalSourceNotFoundError(
                f"Managed source {job.source_id} is not registered in Retrieval"
            )

        self._ensure_job_matches_source(job=job, source=source)

        fingerprint = calculate_index_fingerprint(
            source_sha256=job.source_sha256,
            model_name=self._expected_model,
            vector_dimension=self._expected_dimension,
            chunks=job.chunks,
        )

        if source.state is SourceIndexState.INDEXED and source.active_fingerprint == fingerprint:
            await self._vector_store.delete_obsolete_versions(
                source_id=source.source_id,
                active_fingerprint=fingerprint,
            )
            return SourceIndexResult(
                source_id=source.source_id,
                fingerprint=fingerprint,
                chunk_count=source.chunk_count,
                reused=True,
            )

        embedded = await self._embedding_gateway.embed_texts(
            texts=tuple(chunk.text for chunk in job.chunks),
            instruction=_INDEX_INSTRUCTION,
            correlation_id=job.correlation_id,
        )

        if embedded.model != self._expected_model:
            raise RetrievalEmbeddingError(
                f"Embedding model mismatch: expected {self._expected_model}, got {embedded.model}"
            )

        if embedded.dimension != self._expected_dimension:
            raise RetrievalEmbeddingError(
                "Embedding dimension mismatch: "
                f"expected {self._expected_dimension}, got {embedded.dimension}"
            )

        if len(embedded.vectors) != len(job.chunks):
            raise RetrievalEmbeddingError("Embedding batch size does not match chunk count")

        await self._vector_store.upsert_version(
            source=source,
            fingerprint=fingerprint,
            chunks=job.chunks,
            vectors=embedded.vectors,
        )

        try:
            async with self._uow_factory() as uow:
                locked_source = await uow.source_indexes.get_for_update(job.source_id)

                if locked_source is None:
                    raise RetrievalSourceNotFoundError(
                        f"Managed source {job.source_id} disappeared before activation"
                    )

                self._ensure_job_matches_source(job=job, source=locked_source)

                indexed = locked_source.mark_indexed(
                    fingerprint=fingerprint,
                    model_name=embedded.model,
                    vector_dimension=embedded.dimension,
                    chunk_count=len(job.chunks),
                    changed_at=self._clock.now(),
                )
                await uow.source_indexes.save(indexed)
                await uow.commit()
        except Exception:
            try:
                await self._vector_store.delete_version(
                    source_id=job.source_id,
                    fingerprint=fingerprint,
                )
            except Exception:
                # Candidate без DB activation не участвует в search и может быть
                # дочищен recovery/reindex retry. Не маскируем исходную ошибку.
                pass
            raise

        await self._vector_store.delete_obsolete_versions(
            source_id=job.source_id,
            active_fingerprint=fingerprint,
        )

        return SourceIndexResult(
            source_id=job.source_id,
            fingerprint=fingerprint,
            chunk_count=len(job.chunks),
            reused=False,
        )

    @staticmethod
    def _ensure_job_matches_source(
        *,
        job: IndexSourceJob,
        source: ManagedSourceIndex,
    ) -> None:
        """Проверяет source state/hash перед expensive/commit шагом."""
        if source.state is SourceIndexState.DELETED:
            raise RetrievalSourceConflictError(f"Managed source {job.source_id} is deleted")

        if source.source_sha256 != job.source_sha256:
            raise RetrievalSourceConflictError(
                f"Source hash changed before indexing {job.source_id}"
            )
