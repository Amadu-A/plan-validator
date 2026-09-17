# services/document-service/src/document_service/infrastructure/maintenance.py

"""Periodic retryable cleanup expired/delete-pending Project Documents."""

import asyncio
import logging

from plan_validator_common.observability import configure_logging

from document_service.application.use_cases.documents import DeleteProjectDocumentUseCase
from document_service.core.container import build_container
from document_service.core.settings import load_document_settings


async def run_maintenance() -> None:
    """Запускает bounded cleanup iterations без Rabbit/Celery."""
    settings = load_document_settings()
    configure_logging(
        service_name="document-maintenance",
        level=settings.log_level.value,
        log_root_dir=settings.log_root_dir,
        log_to_file=settings.log_to_file,
        file_max_bytes=settings.log_file_max_bytes,
        file_backup_count=settings.log_file_backup_count,
        retention_days=settings.log_retention_days,
    )
    logger = logging.getLogger(__name__)
    container = build_container(settings)
    try:
        while True:
            async with container.uow_factory() as uow:
                candidates = await uow.documents.list_cleanup_candidates(
                    now=container.clock.now(),
                    limit=settings.document_retention.cleanup_batch_size,
                )
            cleaner = DeleteProjectDocumentUseCase(
                uow_factory=container.uow_factory,
                storage=container.storage,
                clock=container.clock,
            )
            for document in candidates:
                try:
                    await cleaner.execute(
                        user_id=document.user_id,
                        document_id=document.id,
                    )
                except Exception:
                    logger.exception(
                        "Document cleanup iteration failed",
                        extra={
                            "event": "document_cleanup_failed",
                            "document_id": str(document.id),
                        },
                    )
            await asyncio.sleep(settings.document_retention.maintenance_interval_seconds)
    finally:
        await container.aclose()


def main() -> None:
    """CLI entrypoint maintenance process."""
    asyncio.run(run_maintenance())


if __name__ == "__main__":
    main()
