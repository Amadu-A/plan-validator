# services/context-service/src/context_service/infrastructure/messaging/worker.py

"""RabbitMQ worker bounded Context indexing с heartbeat/lease recovery."""

import asyncio
import logging
import os
import signal
import socket
from collections.abc import Awaitable, Callable
from contextlib import suppress
from uuid import UUID

from aio_pika.abc import AbstractIncomingMessage
from plan_validator_common.observability import configure_logging, scoped_log_context
from pydantic import ValidationError

from context_service.application.use_cases.index_jobs import (
    ClaimContextIndexJobUseCase,
    CompleteContextIndexJobUseCase,
    FailContextIndexJobUseCase,
    HeartbeatContextIndexJobUseCase,
)
from context_service.application.use_cases.index_runtime import IndexContextSourceUseCase
from context_service.core.settings import ContextSettings, load_context_settings
from context_service.domain.exceptions import (
    ContextDependencyError,
    ContextIndexJobConflictError,
    ContextIndexJobNotFoundError,
    ContextServiceError,
)
from context_service.infrastructure.clock import SystemClock
from context_service.infrastructure.database.engine import (
    create_context_engine,
    create_context_session_factory,
)
from context_service.infrastructure.database.uow import (
    SqlAlchemyContextUnitOfWorkFactory,
)
from context_service.infrastructure.messaging.embedding_gateway import (
    RabbitContextEmbeddingGateway,
)
from context_service.infrastructure.messaging.rabbitmq import connect_context_broker
from context_service.infrastructure.messaging.schemas import ContextIndexJobMessage
from context_service.infrastructure.vector_store.qdrant import (
    QdrantContextVectorStore,
    build_qdrant_client,
)

_LOGGER = logging.getLogger(__name__)
Handler = Callable[[AbstractIncomingMessage], Awaitable[None]]


class ContextWorkerRuntime:
    """Содержит process-level use-cases одного Context worker."""

    def __init__(
        self,
        *,
        settings: ContextSettings,
        claim: ClaimContextIndexJobUseCase,
        heartbeat: HeartbeatContextIndexJobUseCase,
        fail: FailContextIndexJobUseCase,
        index_source: IndexContextSourceUseCase,
        worker_id: str,
    ) -> None:
        """Сохраняет dependencies без скрытых module-level state."""
        self.settings = settings
        self.claim = claim
        self.heartbeat = heartbeat
        self.fail = fail
        self.index_source = index_source
        self.worker_id = worker_id
        self._active_jobs = 0
        self._idle_event = asyncio.Event()
        self._idle_event.set()

    def job_started(self) -> None:
        """Отмечает active delivery для graceful drain."""
        self._active_jobs += 1
        self._idle_event.clear()

    def job_finished(self) -> None:
        """Освобождает graceful-drain slot после завершения delivery."""
        self._active_jobs = max(0, self._active_jobs - 1)
        if self._active_jobs == 0:
            self._idle_event.set()

    async def wait_idle(self) -> None:
        """Ждёт завершения всех active deliveries."""
        await self._idle_event.wait()


def build_message_handler(runtime: ContextWorkerRuntime) -> Handler:
    """Создаёт idempotent handler persistent job identifiers."""

    async def handle(message: AbstractIncomingMessage) -> None:
        """Claim'ит DB lease, выполняет bounded attempt и всегда завершает delivery."""
        try:
            payload = ContextIndexJobMessage.model_validate_json(message.body)
        except ValidationError as exc:
            await message.reject(requeue=False)
            _LOGGER.error(
                "Context indexing message rejected",
                extra={
                    "event": "context_index_message_rejected",
                    "error_type": type(exc).__name__,
                },
            )
            return

        with scoped_log_context(
            correlation_id=payload.correlation_id,
            job_id=str(payload.job_id),
        ):
            try:
                claim = await runtime.claim.execute(
                    job_id=payload.job_id,
                    worker_id=runtime.worker_id,
                )
            except Exception as exc:
                await _requeue_claim_failure(
                    message=message,
                    job_id=payload.job_id,
                    error=exc,
                )
                return

            if not claim.claimed:
                await message.ack()
                _LOGGER.info(
                    "Context indexing duplicate/non-executable delivery acknowledged",
                    extra={
                        "event": "context_index_delivery_ignored",
                        "job_id": str(payload.job_id),
                        "attempt": claim.job.attempt,
                        "state": claim.job.state.value,
                    },
                )
                return

            runtime.job_started()
            stop_heartbeat = asyncio.Event()
            heartbeat_task = asyncio.create_task(
                _heartbeat_loop(
                    runtime=runtime,
                    job_id=payload.job_id,
                    stop_event=stop_heartbeat,
                ),
                name=f"context-heartbeat-{payload.job_id}",
            )

            try:
                async with asyncio.timeout(
                    runtime.settings.context_queue.execution_timeout_seconds
                ):
                    result = await runtime.index_source.execute(
                        job=claim.job,
                        worker_id=runtime.worker_id,
                    )

                await message.ack()
                _LOGGER.info(
                    "Context indexing attempt completed",
                    extra={
                        "event": "context_index_attempt_completed",
                        "job_id": str(payload.job_id),
                        "attempt": result.attempt,
                        "state": result.state.value,
                    },
                )
            except TimeoutError as exc:
                await _persist_attempt_failure(
                    runtime=runtime,
                    message=message,
                    job_id=payload.job_id,
                    transient=True,
                    error=exc,
                    error_type="ExecutionTimeout",
                )
            except ContextDependencyError as exc:
                await _persist_attempt_failure(
                    runtime=runtime,
                    message=message,
                    job_id=payload.job_id,
                    transient=True,
                    error=exc,
                    error_type=type(exc).__name__,
                )
            except (
                ContextIndexJobConflictError,
                ContextIndexJobNotFoundError,
            ) as exc:
                await message.ack()
                _LOGGER.warning(
                    "Context indexing lease/state changed during attempt",
                    extra={
                        "event": "context_index_lease_changed",
                        "job_id": str(payload.job_id),
                        "error_type": type(exc).__name__,
                    },
                )
            except ContextServiceError as exc:
                await _persist_attempt_failure(
                    runtime=runtime,
                    message=message,
                    job_id=payload.job_id,
                    transient=False,
                    error=exc,
                    error_type=type(exc).__name__,
                )
            except Exception as exc:
                await _persist_attempt_failure(
                    runtime=runtime,
                    message=message,
                    job_id=payload.job_id,
                    transient=False,
                    error=exc,
                    error_type=type(exc).__name__,
                )
            finally:
                stop_heartbeat.set()
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task
                runtime.job_finished()

    return handle


async def _requeue_claim_failure(
    *,
    message: AbstractIncomingMessage,
    job_id: UUID,
    error: Exception,
) -> None:
    """Коротко backoff'ит DB outage и оставляет Rabbit command recoverable."""
    _LOGGER.exception(
        "Context job claim failed before DB lease",
        extra={
            "event": "context_index_claim_failed",
            "job_id": str(job_id),
            "error_type": type(error).__name__,
        },
    )
    await asyncio.sleep(1.0)
    await message.nack(requeue=True)


async def _persist_attempt_failure(
    *,
    runtime: ContextWorkerRuntime,
    message: AbstractIncomingMessage,
    job_id: UUID,
    transient: bool,
    error: Exception,
    error_type: str,
) -> None:
    """Сохраняет retry/terminal state до ACK; stale lease страхует DB failure."""
    try:
        updated = await runtime.fail.execute(
            job_id=job_id,
            worker_id=runtime.worker_id,
            transient=transient,
            error_message=f"{error_type}: {str(error)[:1500]}",
        )
    except ContextIndexJobConflictError:
        await message.ack()
        _LOGGER.warning(
            "Context indexing failure ignored after lease transfer",
            extra={
                "event": "context_index_failure_after_lease_transfer",
                "job_id": str(job_id),
                "error_type": error_type,
            },
        )
        return
    except Exception as persist_error:
        await message.ack()
        _LOGGER.exception(
            "Context failure state persistence failed; stale lease recovery required",
            extra={
                "event": "context_index_failure_persist_failed",
                "job_id": str(job_id),
                "error_type": type(persist_error).__name__,
                "attempt_error_type": error_type,
            },
        )
        return

    await message.ack()
    _LOGGER.error(
        "Context indexing attempt failed",
        extra={
            "event": "context_index_attempt_failed",
            "job_id": str(job_id),
            "attempt": updated.attempt,
            "state": updated.state.value,
            "error_type": error_type,
            "transient": transient,
        },
    )


async def _heartbeat_loop(
    *,
    runtime: ContextWorkerRuntime,
    job_id: UUID,
    stop_event: asyncio.Event,
) -> None:
    """Продлевает process-owned lease пока expensive attempt выполняется."""
    interval = runtime.settings.context_queue.heartbeat_seconds

    while not stop_event.is_set():
        with suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=interval)

        if stop_event.is_set():
            return

        try:
            heartbeat = await runtime.heartbeat.execute(
                job_id=job_id,
                worker_id=runtime.worker_id,
            )
            _LOGGER.debug(
                "Context indexing lease heartbeat",
                extra={
                    "event": "context_index_heartbeat",
                    "job_id": str(job_id),
                    "attempt": heartbeat.attempt,
                    "state": heartbeat.state.value,
                },
            )
        except (
            ContextIndexJobConflictError,
            ContextIndexJobNotFoundError,
        ):
            _LOGGER.warning(
                "Context heartbeat stopped after lease/state change",
                extra={
                    "event": "context_index_heartbeat_stopped",
                    "job_id": str(job_id),
                },
            )
            return
        except Exception as exc:
            _LOGGER.exception(
                "Context heartbeat failed; lease expiry will trigger recovery",
                extra={
                    "event": "context_index_heartbeat_failed",
                    "job_id": str(job_id),
                    "error_type": type(exc).__name__,
                },
            )


def build_runtime(settings: ContextSettings) -> tuple[ContextWorkerRuntime, object, object]:
    """Собирает worker dependencies и возвращает owned engine/Qdrant resources."""
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
    complete = CompleteContextIndexJobUseCase(
        uow_factory=uow_factory,
        clock=clock,
        context_ttl_hours=settings.context_retention.grace_hours,
    )
    runtime = ContextWorkerRuntime(
        settings=settings,
        claim=ClaimContextIndexJobUseCase(
            uow_factory=uow_factory,
            clock=clock,
            lease_seconds=settings.context_queue.lease_seconds,
        ),
        heartbeat=HeartbeatContextIndexJobUseCase(
            uow_factory=uow_factory,
            clock=clock,
            lease_seconds=settings.context_queue.lease_seconds,
        ),
        fail=FailContextIndexJobUseCase(
            uow_factory=uow_factory,
            clock=clock,
            retry_backoff_base_seconds=(settings.context_queue.retry_backoff_base_seconds),
            retry_backoff_max_seconds=(settings.context_queue.retry_backoff_max_seconds),
        ),
        index_source=IndexContextSourceUseCase(
            uow_factory=uow_factory,
            embedding_gateway=RabbitContextEmbeddingGateway(settings),
            vector_store=vector_store,
            complete_job=complete,
            expected_model=settings.context_embedding.model_name,
            expected_dimension=settings.context_embedding.vector_dimension,
            index_instruction=settings.context_embedding.index_instruction,
        ),
        worker_id=f"{socket.gethostname()}:{os.getpid()}",
    )
    return runtime, engine, qdrant_client


async def run_worker(settings: ContextSettings) -> None:
    """Consume'ит dedicated queue с prefetch=1 и graceful channel shutdown."""
    runtime, engine, qdrant_client = build_runtime(settings)
    connection = await connect_context_broker(settings)

    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=settings.context_queue.prefetch_count)
        queue = await channel.declare_queue(
            settings.context_queue.index_queue_name,
            durable=True,
            auto_delete=False,
        )
        consumer_tag = await queue.consume(
            build_message_handler(runtime),
            no_ack=False,
        )
        shutdown_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        def request_shutdown() -> None:
            """Перестаёт принимать новые jobs и запускает graceful drain."""
            shutdown_event.set()

        for handled_signal in (signal.SIGTERM, signal.SIGINT):
            with suppress(NotImplementedError):
                loop.add_signal_handler(handled_signal, request_shutdown)

        _LOGGER.info(
            "Context worker started",
            extra={
                "event": "context_worker_started",
                "queue": settings.context_queue.index_queue_name,
                "prefetch_count": settings.context_queue.prefetch_count,
                "worker_id": runtime.worker_id,
            },
        )
        await shutdown_event.wait()
        await queue.cancel(consumer_tag)

        try:
            await asyncio.wait_for(
                runtime.wait_idle(),
                timeout=settings.context_queue.graceful_shutdown_seconds,
            )
        except TimeoutError:
            _LOGGER.warning(
                "Context worker graceful drain timed out",
                extra={
                    "event": "context_worker_drain_timeout",
                    "timeout_seconds": (settings.context_queue.graceful_shutdown_seconds),
                },
            )
        else:
            _LOGGER.info(
                "Context worker graceful drain completed",
                extra={"event": "context_worker_drain_completed"},
            )
    finally:
        await connection.close()
        await qdrant_client.close()
        await engine.dispose()


def main() -> None:
    """Настраивает structured logging и запускает Context worker."""
    settings = load_context_settings()
    configure_logging(
        service_name="context-worker",
        level=settings.log_level.value,
        log_root_dir=settings.log_root_dir,
        log_to_file=settings.log_to_file,
        file_max_bytes=settings.log_file_max_bytes,
        file_backup_count=settings.log_file_backup_count,
        retention_days=settings.log_retention_days,
    )
    asyncio.run(run_worker(settings))


if __name__ == "__main__":
    main()
