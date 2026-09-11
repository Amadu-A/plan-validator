# services/context-service/src/context_service/infrastructure/messaging/reconciler.py

"""Periodic DB-driven reconciliation lost/stale Context indexing jobs."""

import asyncio
import logging

from plan_validator_common.observability import configure_logging

from context_service.application.use_cases.index_jobs import (
    FailContextIndexJobUseCase,
    ReconcileContextIndexJobsUseCase,
)
from context_service.core.settings import ContextSettings, load_context_settings
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

_LOGGER = logging.getLogger(__name__)


async def run_reconciler(settings: ContextSettings) -> None:
    """Периодически восстанавливает jobs без зависимости от worker process."""
    engine = create_context_engine(settings)
    session_factory = create_context_session_factory(engine)
    uow_factory = SqlAlchemyContextUnitOfWorkFactory(session_factory)
    clock = SystemClock()
    failure = FailContextIndexJobUseCase(
        uow_factory=uow_factory,
        clock=clock,
        retry_backoff_base_seconds=settings.context_queue.retry_backoff_base_seconds,
        retry_backoff_max_seconds=settings.context_queue.retry_backoff_max_seconds,
    )
    reconcile = ReconcileContextIndexJobsUseCase(
        uow_factory=uow_factory,
        publisher=RabbitContextIndexJobPublisher(settings),
        clock=clock,
        retry_failure=failure,
        batch_size=settings.context_queue.reconciliation_batch_size,
    )

    _LOGGER.info(
        "Context reconciler started",
        extra={
            "event": "context_reconciler_started",
            "interval_seconds": settings.context_queue.reconcile_seconds,
        },
    )

    try:
        while True:
            try:
                result = await reconcile.execute()
                if result.inspected:
                    _LOGGER.info(
                        "Context reconciliation iteration completed",
                        extra={
                            "event": "context_reconciliation_completed",
                            "inspected": result.inspected,
                            "dispatched": result.dispatched,
                            "publish_failed": result.publish_failed,
                            "terminalized": result.terminalized,
                        },
                    )
            except Exception as exc:
                _LOGGER.exception(
                    "Context reconciliation iteration failed",
                    extra={
                        "event": "context_reconciliation_failed",
                        "error_type": type(exc).__name__,
                    },
                )

            await asyncio.sleep(settings.context_queue.reconcile_seconds)
    finally:
        await engine.dispose()


def main() -> None:
    """Настраивает structured logging и запускает reconciler loop."""
    settings = load_context_settings()
    configure_logging(
        service_name="context-reconciler",
        level=settings.log_level.value,
        log_root_dir=settings.log_root_dir,
        log_to_file=settings.log_to_file,
        file_max_bytes=settings.log_file_max_bytes,
        file_backup_count=settings.log_file_backup_count,
        retention_days=settings.log_retention_days,
    )
    asyncio.run(run_reconciler(settings))


if __name__ == "__main__":
    main()
