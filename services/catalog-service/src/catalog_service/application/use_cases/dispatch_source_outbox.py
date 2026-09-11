# services/catalog-service/src/catalog_service/application/use_cases/dispatch_source_outbox.py

"""Use-case доставки одного Catalog transactional outbox message."""

from plan_validator_common.observability import log_execution_time

from catalog_service.application.ports.clock import Clock
from catalog_service.application.ports.source_event_publisher import (
    SourceEventPublisher,
    SourceEventPublishError,
)
from catalog_service.application.ports.unit_of_work import CatalogUnitOfWorkFactory


class DispatchNextSourceOutboxMessageUseCase:
    """Доставляет oldest unpublished event и фиксирует publisher confirm."""

    def __init__(
        self,
        *,
        uow_factory: CatalogUnitOfWorkFactory,
        publisher: SourceEventPublisher,
        clock: Clock,
    ) -> None:
        """Сохраняет transactional dependencies dispatcher."""
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._clock = clock

    @log_execution_time("catalog.dispatch_source_outbox")
    async def execute(self) -> bool:
        """Возвращает False при пустом outbox, иначе доставляет одно event."""
        async with self._uow_factory() as uow:
            message = await uow.source_outbox.get_next_pending_for_update()

            if message is None:
                return False

            try:
                await self._publisher.publish(message)
            except SourceEventPublishError as exc:
                await uow.source_outbox.mark_failed(
                    message_id=message.id,
                    error_message=str(exc)[:2000],
                )
                await uow.commit()
                raise

            await uow.source_outbox.mark_published(
                message_id=message.id,
                published_at=self._clock.now(),
            )
            await uow.commit()

            return True
