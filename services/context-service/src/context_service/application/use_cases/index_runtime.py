# services/context-service/src/context_service/application/use_cases/index_runtime.py

"""Crash-safe runtime indexing одного claimed Context job."""

from contextlib import suppress

from plan_validator_common.observability import log_execution_time

from context_service.application.ports.embedding_gateway import ContextEmbeddingGateway
from context_service.application.ports.unit_of_work import ContextUnitOfWorkFactory
from context_service.application.ports.vector_store import ContextVectorStore
from context_service.application.use_cases.index_jobs import (
    CompleteContextIndexJobUseCase,
)
from context_service.domain.exceptions import (
    ContextEmbeddingError,
    ContextIndexJobConflictError,
    ContextSourceConflictError,
    ContextSourceNotFoundError,
    ProjectContextNotFoundError,
)
from context_service.domain.models import (
    ContextIndexJob,
    ContextIndexJobState,
    ContextSourceState,
    ProjectContextState,
)


class IndexContextSourceUseCase:
    """Выполняет embed -> candidate upsert -> DB activation -> stale cleanup."""

    def __init__(
        self,
        *,
        uow_factory: ContextUnitOfWorkFactory,
        embedding_gateway: ContextEmbeddingGateway,
        vector_store: ContextVectorStore,
        complete_job: CompleteContextIndexJobUseCase,
        expected_model: str,
        expected_dimension: int,
        index_instruction: str,
    ) -> None:
        """Сохраняет runtime dependencies и embedding compatibility contract."""
        self._uow_factory = uow_factory
        self._embedding_gateway = embedding_gateway
        self._vector_store = vector_store
        self._complete_job = complete_job
        self._expected_model = expected_model
        self._expected_dimension = expected_dimension
        self._index_instruction = index_instruction

    @log_execution_time("context.index_source_runtime")
    async def execute(
        self,
        *,
        job: ContextIndexJob,
        worker_id: str,
    ) -> ContextIndexJob:
        """Выполняет один process-owned indexing attempt."""
        if job.state is not ContextIndexJobState.RUNNING:
            raise ContextIndexJobConflictError("Context indexing job is not running")
        if job.lease_owner != worker_id:
            raise ContextIndexJobConflictError(
                "Context indexing job lease belongs to another worker"
            )

        async with self._uow_factory() as uow:
            context = await uow.contexts.get_for_user(
                user_id=job.user_id,
                context_id=job.context_id,
            )
            source = await uow.sources.get_for_user(
                user_id=job.user_id,
                source_id=job.source_id,
            )

        if context is None:
            raise ProjectContextNotFoundError("Project Context was not found")
        if source is None or source.context_id != job.context_id:
            raise ContextSourceNotFoundError("Context source was not found")

        if context.state is not ProjectContextState.ACTIVE:
            return await self._complete_job.execute(
                job_id=job.id,
                worker_id=worker_id,
            )

        if source.state is ContextSourceState.DELETED:
            raise ContextSourceConflictError("Context source is deleted")

        if (
            source.state is ContextSourceState.INDEXED
            and source.active_fingerprint == job.fingerprint
        ):
            completed = await self._complete_job.execute(
                job_id=job.id,
                worker_id=worker_id,
            )
            if completed.state is ContextIndexJobState.SUCCEEDED:
                await self._vector_store.delete_obsolete_versions(
                    context_id=job.context_id,
                    kind=job.kind,
                    source_id=job.source_id,
                    active_fingerprint=job.fingerprint,
                )
            return completed

        embedded = await self._embedding_gateway.embed_texts(
            texts=tuple(chunk.text for chunk in job.chunks),
            instruction=self._index_instruction,
            correlation_id=job.correlation_id,
        )
        self._validate_embedding_result(
            model=embedded.model,
            dimension=embedded.dimension,
            vector_count=len(embedded.vectors),
            chunk_count=len(job.chunks),
        )

        await self._vector_store.upsert_version(
            source=source,
            fingerprint=job.fingerprint,
            chunks=job.chunks,
            vectors=embedded.vectors,
        )

        try:
            completed = await self._complete_job.execute(
                job_id=job.id,
                worker_id=worker_id,
            )
        except Exception:
            with suppress(Exception):
                await self._vector_store.delete_version(
                    context_id=job.context_id,
                    kind=job.kind,
                    source_id=job.source_id,
                    fingerprint=job.fingerprint,
                )
            raise

        if completed.state is not ContextIndexJobState.SUCCEEDED:
            with suppress(Exception):
                await self._vector_store.delete_version(
                    context_id=job.context_id,
                    kind=job.kind,
                    source_id=job.source_id,
                    fingerprint=job.fingerprint,
                )
            return completed

        await self._vector_store.delete_obsolete_versions(
            context_id=job.context_id,
            kind=job.kind,
            source_id=job.source_id,
            active_fingerprint=job.fingerprint,
        )
        return completed

    def _validate_embedding_result(
        self,
        *,
        model: str,
        dimension: int,
        vector_count: int,
        chunk_count: int,
    ) -> None:
        """Не допускает silent embedding model/dimension drift."""
        if model != self._expected_model:
            raise ContextEmbeddingError(
                f"Embedding model mismatch: expected {self._expected_model}, got {model}"
            )
        if dimension != self._expected_dimension:
            raise ContextEmbeddingError(
                "Embedding dimension mismatch: "
                f"expected {self._expected_dimension}, got {dimension}"
            )
        if vector_count != chunk_count:
            raise ContextEmbeddingError("Embedding vector count does not match Context chunk count")
