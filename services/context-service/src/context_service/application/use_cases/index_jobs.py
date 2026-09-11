# services/context-service/src/context_service/application/use_cases/index_jobs.py

"""Use-cases durable Context indexing jobs, lease и reconciliation."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from plan_validator_common.observability import log_execution_time

from context_service.application.ports.clock import Clock
from context_service.application.ports.job_publisher import ContextIndexJobPublisher
from context_service.application.ports.unit_of_work import ContextUnitOfWorkFactory
from context_service.domain.exceptions import (
    ContextIndexJobConflictError,
    ContextIndexJobNotFoundError,
    ContextJobPublishError,
    ContextSourceConflictError,
    ContextSourceNotFoundError,
    ProjectContextConflictError,
    ProjectContextNotFoundError,
)
from context_service.domain.models import (
    ContextIndexJob,
    ContextIndexJobState,
    ContextSourceState,
    NormalizedContextChunk,
    ProjectContextState,
    build_context_index_fingerprint,
    validate_chunks,
)

IdentifierFactory = Callable[[], UUID]


@dataclass(frozen=True, slots=True)
class EnqueueContextIndexResult:
    """Результат idempotent enqueue operation."""

    job_id: UUID | None
    fingerprint: str
    reused: bool


@dataclass(frozen=True, slots=True)
class ClaimContextIndexResult:
    """Результат atomic worker claim."""

    job: ContextIndexJob
    claimed: bool


@dataclass(frozen=True, slots=True)
class ReconcileContextJobsResult:
    """Сводка одной bounded reconciliation iteration."""

    inspected: int
    dispatched: int
    publish_failed: int
    terminalized: int


class EnqueueContextIndexUseCase:
    """Создаёт durable job до Rabbit publish и допускает recovery publish failure."""

    def __init__(
        self,
        *,
        uow_factory: ContextUnitOfWorkFactory,
        publisher: ContextIndexJobPublisher,
        clock: Clock,
        model_name: str,
        vector_dimension: int,
        max_chunks: int,
        max_chunk_chars: int,
        max_attempts: int,
        deadline_seconds: int,
        identifier_factory: IdentifierFactory = uuid4,
    ) -> None:
        """Сохраняет durable enqueue dependencies."""
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._clock = clock
        self._model_name = model_name
        self._vector_dimension = vector_dimension
        self._max_chunks = max_chunks
        self._max_chunk_chars = max_chunk_chars
        self._max_attempts = max_attempts
        self._deadline_seconds = deadline_seconds
        self._identifier_factory = identifier_factory

    @log_execution_time("context.enqueue_index")
    async def execute(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
        source_id: UUID,
        chunks: tuple[NormalizedContextChunk, ...],
        correlation_id: str,
    ) -> EnqueueContextIndexResult:
        """Создаёт или переиспользует indexing request."""
        validate_chunks(
            chunks,
            max_chunks=self._max_chunks,
            max_text_chars=self._max_chunk_chars,
        )

        now = self._clock.now()

        async with self._uow_factory() as uow:
            context = await uow.contexts.get_for_user(
                user_id=user_id,
                context_id=context_id,
            )

            if context is None:
                raise ProjectContextNotFoundError("Project Context was not found")

            if context.state is not ProjectContextState.ACTIVE:
                raise ProjectContextConflictError("Project Context is not active")

            source = await uow.sources.get_for_user(
                user_id=user_id,
                source_id=source_id,
            )

            if source is None or source.context_id != context_id:
                raise ContextSourceNotFoundError("Context source was not found")

            if source.state is ContextSourceState.DELETED:
                raise ContextSourceConflictError("Context source is deleted")

            fingerprint = build_context_index_fingerprint(
                source_sha256=source.source_sha256,
                model_name=self._model_name,
                vector_dimension=self._vector_dimension,
                chunks=chunks,
            )

            if (
                source.state is ContextSourceState.INDEXED
                and source.active_fingerprint == fingerprint
            ):
                return EnqueueContextIndexResult(
                    job_id=None,
                    fingerprint=fingerprint,
                    reused=True,
                )

            existing = await uow.jobs.find_open_for_source_fingerprint(
                source_id=source_id,
                fingerprint=fingerprint,
            )

            if existing is not None:
                return EnqueueContextIndexResult(
                    job_id=existing.id,
                    fingerprint=fingerprint,
                    reused=False,
                )

            job = ContextIndexJob(
                id=self._identifier_factory(),
                context_id=context_id,
                source_id=source_id,
                user_id=user_id,
                kind=source.kind,
                fingerprint=fingerprint,
                correlation_id=correlation_id,
                chunks=chunks,
                state=ContextIndexJobState.QUEUED,
                attempt=0,
                max_attempts=self._max_attempts,
                deadline_at=now + timedelta(seconds=self._deadline_seconds),
                next_attempt_at=None,
                dispatched_at=None,
                lease_owner=None,
                lease_expires_at=None,
                last_error=None,
                created_at=now,
                updated_at=now,
            )

            await uow.jobs.add(job)
            await uow.commit()

        await self._publish_and_mark(job)

        return EnqueueContextIndexResult(
            job_id=job.id,
            fingerprint=fingerprint,
            reused=False,
        )

    async def _publish_and_mark(
        self,
        job: ContextIndexJob,
    ) -> None:
        """Публикует job после commit; failed publish оставляет recoverable row."""
        try:
            await self._publisher.publish(
                job_id=job.id,
                correlation_id=job.correlation_id,
            )
        except Exception as exc:
            raise ContextJobPublishError(
                "Context indexing job is durable but Rabbit publish failed"
            ) from exc

        async with self._uow_factory() as uow:
            current = await uow.jobs.get_for_update(job.id)

            if current is None:
                raise ContextIndexJobNotFoundError("Context indexing job disappeared")

            await uow.jobs.save(
                current.mark_dispatched(
                    changed_at=self._clock.now(),
                )
            )
            await uow.commit()


class ClaimContextIndexJobUseCase:
    """Идемпотентно получает process-owned lease одного delivery."""

    def __init__(
        self,
        *,
        uow_factory: ContextUnitOfWorkFactory,
        clock: Clock,
        lease_seconds: int,
    ) -> None:
        """Сохраняет lease dependencies."""
        self._uow_factory = uow_factory
        self._clock = clock
        self._lease_seconds = lease_seconds

    @log_execution_time("context.claim_index_job")
    async def execute(
        self,
        *,
        job_id: UUID,
        worker_id: str,
    ) -> ClaimContextIndexResult:
        """Claim'ит job либо безопасно возвращает claimed=False."""
        async with self._uow_factory() as uow:
            job = await uow.jobs.get_for_update(job_id)

            if job is None:
                raise ContextIndexJobNotFoundError("Context indexing job was not found")

            claimed_job, claimed = job.claim(
                worker_id=worker_id,
                changed_at=self._clock.now(),
                lease_seconds=self._lease_seconds,
            )

            if claimed_job != job:
                await uow.jobs.save(claimed_job)
                await uow.commit()

            return ClaimContextIndexResult(
                job=claimed_job,
                claimed=claimed,
            )


class HeartbeatContextIndexJobUseCase:
    """Продлевает lease активного worker process."""

    def __init__(
        self,
        *,
        uow_factory: ContextUnitOfWorkFactory,
        clock: Clock,
        lease_seconds: int,
    ) -> None:
        """Сохраняет heartbeat dependencies."""
        self._uow_factory = uow_factory
        self._clock = clock
        self._lease_seconds = lease_seconds

    async def execute(
        self,
        *,
        job_id: UUID,
        worker_id: str,
    ) -> ContextIndexJob:
        """Продлевает только принадлежащий текущему worker lease."""
        async with self._uow_factory() as uow:
            job = await uow.jobs.get_for_update(job_id)

            if job is None:
                raise ContextIndexJobNotFoundError("Context indexing job was not found")

            updated = job.heartbeat(
                worker_id=worker_id,
                changed_at=self._clock.now(),
                lease_seconds=self._lease_seconds,
            )
            await uow.jobs.save(updated)
            await uow.commit()

        return updated


class CompleteContextIndexJobUseCase:
    """Атомарно активирует source fingerprint и завершает persistent job."""

    def __init__(
        self,
        *,
        uow_factory: ContextUnitOfWorkFactory,
        clock: Clock,
        context_ttl_hours: int,
    ) -> None:
        """Сохраняет completion dependencies."""
        self._uow_factory = uow_factory
        self._clock = clock
        self._context_ttl = timedelta(hours=context_ttl_hours)

    @log_execution_time("context.complete_index_job")
    async def execute(
        self,
        *,
        job_id: UUID,
        worker_id: str,
    ) -> ContextIndexJob:
        """Активирует fingerprint только для текущего lease owner."""
        now = self._clock.now()

        async with self._uow_factory() as uow:
            job = await uow.jobs.get_for_update(job_id)

            if job is None:
                raise ContextIndexJobNotFoundError("Context indexing job was not found")

            if job.state is not ContextIndexJobState.RUNNING:
                if job.state is ContextIndexJobState.SUCCEEDED:
                    return job

                raise ContextIndexJobConflictError("Context indexing job is not running")

            if job.lease_owner != worker_id:
                raise ContextIndexJobConflictError(
                    "Context indexing job lease belongs to another worker"
                )

            if now >= job.deadline_at:
                failed = job.fail(
                    changed_at=now,
                    error_message="job_deadline_exceeded_before_activation",
                )
                await uow.jobs.save(failed)
                await uow.commit()
                return failed

            source = await uow.sources.get_for_user_for_update(
                user_id=job.user_id,
                source_id=job.source_id,
            )

            if source is None:
                raise ContextSourceNotFoundError("Context source was not found")

            context = await uow.contexts.get_for_user_for_update(
                user_id=job.user_id,
                context_id=job.context_id,
            )

            if context is None:
                raise ProjectContextNotFoundError("Project Context was not found")

            if context.state is not ProjectContextState.ACTIVE:
                canceled = job.cancel(
                    changed_at=now,
                    reason="project_context_not_active",
                )
                await uow.jobs.save(canceled)
                await uow.commit()
                return canceled

            indexed_source = source.mark_indexed(
                fingerprint=job.fingerprint,
                chunk_count=len(job.chunks),
                changed_at=now,
            )
            succeeded = job.succeed(
                changed_at=now,
            )

            await uow.sources.save(indexed_source)
            await uow.contexts.save(
                context.touch(
                    changed_at=now,
                    ttl=self._context_ttl,
                )
            )
            await uow.jobs.save(succeeded)
            await uow.commit()

        return succeeded


class FailContextIndexJobUseCase:
    """Различает transient failure и terminal failure."""

    def __init__(
        self,
        *,
        uow_factory: ContextUnitOfWorkFactory,
        clock: Clock,
        retry_backoff_base_seconds: int,
        retry_backoff_max_seconds: int,
    ) -> None:
        """Сохраняет retry policy."""
        self._uow_factory = uow_factory
        self._clock = clock
        self._retry_backoff_base_seconds = retry_backoff_base_seconds
        self._retry_backoff_max_seconds = retry_backoff_max_seconds

    @log_execution_time("context.fail_index_job")
    async def execute(
        self,
        *,
        job_id: UUID,
        worker_id: str | None,
        transient: bool,
        error_message: str,
        immediate_retry: bool = False,
    ) -> ContextIndexJob:
        """Планирует bounded retry либо terminal failure."""
        now = self._clock.now()

        async with self._uow_factory() as uow:
            job = await uow.jobs.get_for_update(job_id)

            if job is None:
                raise ContextIndexJobNotFoundError("Context indexing job was not found")

            if job.is_terminal:
                return job

            if (
                worker_id is not None
                and job.state is ContextIndexJobState.RUNNING
                and job.lease_owner != worker_id
            ):
                raise ContextIndexJobConflictError(
                    "Context indexing job lease belongs to another worker"
                )

            can_retry = transient and job.attempt < job.max_attempts and now < job.deadline_at

            if not can_retry:
                updated = job.fail(
                    changed_at=now,
                    error_message=error_message,
                )
            else:
                delay_seconds = 0 if immediate_retry else self._retry_delay_seconds(job.attempt)
                next_attempt_at = now + timedelta(seconds=delay_seconds)

                if next_attempt_at >= job.deadline_at:
                    updated = job.fail(
                        changed_at=now,
                        error_message="retry_would_exceed_job_deadline",
                    )
                else:
                    updated = job.schedule_retry(
                        changed_at=now,
                        next_attempt_at=next_attempt_at,
                        error_message=error_message,
                    )

            await uow.jobs.save(updated)
            await uow.commit()

        return updated

    def _retry_delay_seconds(
        self,
        attempt: int,
    ) -> int:
        """Возвращает bounded exponential backoff."""
        exponent = max(attempt - 1, 0)
        calculated = self._retry_backoff_base_seconds * 2**exponent
        return min(
            calculated,
            self._retry_backoff_max_seconds,
        )


class ReconcileContextIndexJobsUseCase:
    """Восстанавливает lost publish и stale RUNNING после crash/restart."""

    def __init__(
        self,
        *,
        uow_factory: ContextUnitOfWorkFactory,
        publisher: ContextIndexJobPublisher,
        clock: Clock,
        retry_failure: FailContextIndexJobUseCase,
        redispatch_seconds: int,
        batch_size: int,
    ) -> None:
        """Сохраняет reconciliation dependencies."""
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._clock = clock
        self._retry_failure = retry_failure
        self._redispatch_seconds = redispatch_seconds
        self._batch_size = batch_size

    @log_execution_time("context.reconcile_index_jobs")
    async def execute(self) -> ReconcileContextJobsResult:
        """Выполняет одну bounded reconciliation iteration."""
        now = self._clock.now()
        redispatch_before = now - timedelta(seconds=self._redispatch_seconds)

        async with self._uow_factory() as uow:
            candidates = await uow.jobs.list_recoverable(
                now=now,
                redispatch_before=redispatch_before,
                limit=self._batch_size,
            )

        dispatched = 0
        publish_failed = 0
        terminalized = 0

        for candidate in candidates:
            job = candidate

            if now >= job.deadline_at:
                await self._terminalize_deadline(job.id)
                terminalized += 1
                continue

            if (
                job.state is ContextIndexJobState.RUNNING
                and job.lease_expires_at is not None
                and job.lease_expires_at <= now
            ):
                job = await self._retry_failure.execute(
                    job_id=job.id,
                    worker_id=None,
                    transient=True,
                    error_message="stale_worker_lease_recovered",
                    immediate_retry=True,
                )

                if job.state is ContextIndexJobState.FAILED:
                    terminalized += 1
                    continue

            if job.state not in {
                ContextIndexJobState.QUEUED,
                ContextIndexJobState.RETRY_WAIT,
            }:
                continue

            if job.next_attempt_at is not None and job.next_attempt_at > now:
                continue

            try:
                await self._publisher.publish(
                    job_id=job.id,
                    correlation_id=job.correlation_id,
                )
            except Exception:
                publish_failed += 1
                continue

            await self._mark_dispatched(job.id)
            dispatched += 1

        return ReconcileContextJobsResult(
            inspected=len(candidates),
            dispatched=dispatched,
            publish_failed=publish_failed,
            terminalized=terminalized,
        )

    async def _mark_dispatched(
        self,
        job_id: UUID,
    ) -> None:
        """Фиксирует successful republish без удержания DB lock на network I/O."""
        async with self._uow_factory() as uow:
            job = await uow.jobs.get_for_update(job_id)

            if job is None or job.is_terminal:
                return

            await uow.jobs.save(
                job.mark_dispatched(
                    changed_at=self._clock.now(),
                )
            )
            await uow.commit()

    async def _terminalize_deadline(
        self,
        job_id: UUID,
    ) -> None:
        """Фиксирует абсолютный deadline независимо от Rabbit state."""
        async with self._uow_factory() as uow:
            job = await uow.jobs.get_for_update(job_id)

            if job is None or job.is_terminal:
                return

            await uow.jobs.save(
                job.fail(
                    changed_at=self._clock.now(),
                    error_message="job_deadline_exceeded",
                )
            )
            await uow.commit()
