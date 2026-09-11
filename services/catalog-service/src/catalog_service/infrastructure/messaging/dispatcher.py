# services/catalog-service/src/catalog_service/infrastructure/messaging/dispatcher.py

"""Process entrypoint Catalog transactional outbox dispatcher."""

import asyncio
import logging

from plan_validator_common.observability import configure_logging

from catalog_service.application.ports.source_event_publisher import SourceEventPublishError
from catalog_service.application.use_cases.dispatch_source_outbox import (
    DispatchNextSourceOutboxMessageUseCase,
)
from catalog_service.core.settings import (
    CatalogOutboxProcessSettings,
    load_catalog_outbox_settings,
)
from catalog_service.infrastructure.clock import SystemClock
from catalog_service.infrastructure.database.engine import (
    create_catalog_engine,
    create_catalog_session_factory,
)
from catalog_service.infrastructure.database.uow import SqlAlchemyCatalogUnitOfWorkFactory
from catalog_service.infrastructure.messaging.source_event_publisher import (
    RabbitSourceEventPublisher,
)

_LOGGER = logging.getLogger(__name__)


async def run_dispatcher(settings: CatalogOutboxProcessSettings) -> None:
    """Постоянно доставляет pending outbox events с bounded idle/backoff delay."""
    engine = create_catalog_engine(settings)
    session_factory = create_catalog_session_factory(engine)
    uow_factory = SqlAlchemyCatalogUnitOfWorkFactory(session_factory)
    publisher = await RabbitSourceEventPublisher.create(settings)
    use_case = DispatchNextSourceOutboxMessageUseCase(
        uow_factory=uow_factory,
        publisher=publisher,
        clock=SystemClock(),
    )

    _LOGGER.info(
        "Catalog outbox dispatcher started",
        extra={
            "event": "catalog_outbox_started",
            "exchange": settings.catalog_outbox.exchange_name,
        },
    )

    try:
        while True:
            try:
                dispatched = await use_case.execute()
            except SourceEventPublishError:
                _LOGGER.warning(
                    "Catalog source event delivery failed; retry scheduled",
                    extra={"event": "catalog_outbox_publish_failed"},
                )
                await asyncio.sleep(settings.catalog_outbox.failure_backoff_seconds)
                continue

            if not dispatched:
                await asyncio.sleep(settings.catalog_outbox.poll_seconds)
    finally:
        await publisher.aclose()
        await engine.dispose()


def main() -> None:
    """Настраивает structured logging и запускает dispatcher loop."""
    settings = load_catalog_outbox_settings()
    configure_logging(
        service_name=settings.service_name,
        level=settings.log_level.value,
        log_root_dir=settings.log_root_dir,
        log_to_file=settings.log_to_file,
        file_max_bytes=settings.log_file_max_bytes,
        file_backup_count=settings.log_file_backup_count,
        retention_days=settings.log_retention_days,
    )
    asyncio.run(run_dispatcher(settings))


if __name__ == "__main__":
    main()
