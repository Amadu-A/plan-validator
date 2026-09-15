# services/context-service/src/context_service/infrastructure/messaging/maintenance.py

"""Periodic reconciliation и lifecycle cleanup временного Project Context."""

import asyncio
import logging
import signal
from contextlib import suppress

from plan_validator_common.observability import configure_logging

from context_service.application.use_cases.cleanup_context import (
    FinalizeProjectContextCleanupUseCase,
    ListProjectContextCleanupCandidatesUseCase,
)
from context_service.application.use_cases.index_jobs import (
    FailContextIndexJobUseCase,
    ReconcileContextIndexJobsUseCase,
)
from context_service.core.settings import ContextSettings, load_context_settings
from context_service.domain.models import ProjectContextState
from context_service.infrastructure.clock import SystemClock
from context_service.infrastructure.database.engine import (
    create_context_engine,
    create_context_session_factory,
)
from context_service.infrastructure.database.uow import (
    SqlAlchemyContextUnitOfWorkFactory,
)
from context_service.infrastructure.messaging.job_publisher import (
    RabbitContextIndexJobPublisher,
)
from context_service.infrastructure.vector_store.qdrant import (
    QdrantContextVectorStore,
    build_qdrant_client,
)

_LOGGER = logging.getLogger(__name__)


async def run_maintenance(settings: ContextSettings) -> None:
    """Восстанавливает jobs и очищает expired/retryable contexts."""
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

    failure = FailContextIndexJobUseCase(
        uow_factory=uow_factory,
        clock=clock,
        retry_backoff_base_seconds=(settings.context_queue.retry_backoff_base_seconds),
        retry_backoff_max_seconds=settings.context_queue.retry_backoff_max_seconds,
    )

    reconcile = ReconcileContextIndexJobsUseCase(
        uow_factory=uow_factory,
        publisher=RabbitContextIndexJobPublisher(settings),
        clock=clock,
        retry_failure=failure,
        batch_size=settings.context_queue.reconciliation_batch_size,
    )

    list_cleanup = ListProjectContextCleanupCandidatesUseCase(
        uow_factory=uow_factory,
        clock=clock,
        batch_size=settings.context_queue.reconciliation_batch_size,
    )

    finalize_cleanup = FinalizeProjectContextCleanupUseCase(
        uow_factory=uow_factory,
        vector_store=vector_store,
        clock=clock,
    )

    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_shutdown() -> None:
        """Просит maintenance завершиться после текущей bounded iteration."""
        shutdown_event.set()

    for handled_signal in (
        signal.SIGTERM,
        signal.SIGINT,
    ):
        with suppress(NotImplementedError):
            loop.add_signal_handler(
                handled_signal,
                request_shutdown,
            )

    _LOGGER.info(
        "Context maintenance started",
        extra={
            "event": "context_maintenance_started",
            "interval_seconds": settings.context_queue.reconcile_seconds,
        },
    )

    try:
        while not shutdown_event.is_set():
            await _run_reconciliation_iteration(reconcile)

            await _run_cleanup_iteration(
                list_cleanup=list_cleanup,
                finalize_cleanup=finalize_cleanup,
            )

            with suppress(TimeoutError):
                await asyncio.wait_for(
                    shutdown_event.wait(),
                    timeout=settings.context_queue.reconcile_seconds,
                )

    finally:
        _LOGGER.info(
            "Context maintenance stopped",
            extra={
                "event": "context_maintenance_stopped",
            },
        )

        await qdrant_client.close()
        await engine.dispose()


async def _run_reconciliation_iteration(
    reconcile: ReconcileContextIndexJobsUseCase,
) -> None:
    """Выполняет одну failure-isolated job reconciliation iteration."""
    try:
        result = await reconcile.execute()

    except Exception as exc:
        _LOGGER.exception(
            "Context job reconciliation iteration failed",
            extra={
                "event": "context_reconciliation_failed",
                "error_type": type(exc).__name__,
            },
        )

        return

    if not result.inspected:
        return

    _LOGGER.info(
        "Context job reconciliation iteration completed",
        extra={
            "event": "context_reconciliation_completed",
            "inspected": result.inspected,
            "dispatched": result.dispatched,
            "publish_failed": result.publish_failed,
            "terminalized": result.terminalized,
        },
    )


async def _run_cleanup_iteration(
    *,
    list_cleanup: ListProjectContextCleanupCandidatesUseCase,
    finalize_cleanup: FinalizeProjectContextCleanupUseCase,
) -> None:
    """Выполняет retry-safe cleanup каждого candidate независимо."""
    try:
        candidates = await list_cleanup.execute()

    except Exception as exc:
        _LOGGER.exception(
            "Context cleanup candidate scan failed",
            extra={
                "event": "context_cleanup_scan_failed",
                "error_type": type(exc).__name__,
            },
        )

        return

    for context in candidates:
        try:
            result = await finalize_cleanup.execute(
                user_id=context.user_id,
                context_id=context.id,
            )

        except Exception as exc:
            _LOGGER.exception(
                "Project Context cleanup attempt failed",
                extra={
                    "event": "context_cleanup_attempt_failed",
                    "context_id": str(context.id),
                    "error_type": type(exc).__name__,
                },
            )

            continue

        if result.state is ProjectContextState.CLEANED:
            _LOGGER.info(
                "Project Context cleanup completed",
                extra={
                    "event": "context_cleanup_completed",
                    "context_id": str(result.id),
                    "state": result.state.value,
                },
            )

        else:
            _LOGGER.debug(
                "Project Context cleanup remains pending",
                extra={
                    "event": "context_cleanup_pending",
                    "context_id": str(result.id),
                    "state": result.state.value,
                },
            )


def main() -> None:
    """Настраивает structured logging и запускает maintenance process."""
    settings = load_context_settings()

    configure_logging(
        service_name="context-maintenance",
        level=settings.log_level.value,
        log_root_dir=settings.log_root_dir,
        log_to_file=settings.log_to_file,
        file_max_bytes=settings.log_file_max_bytes,
        file_backup_count=settings.log_file_backup_count,
        retention_days=settings.log_retention_days,
    )

    asyncio.run(run_maintenance(settings))


if __name__ == "__main__":
    main()
