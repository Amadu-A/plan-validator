# services/catalog-service/src/catalog_service/application/source_tree.py

"""Application helpers синхронизации filesystem дерева Catalog."""

import logging
from contextlib import suppress
from uuid import UUID

from catalog_service.application.ports.source_storage import (
    SourceStorage,
    SourceStorageError,
)
from catalog_service.domain.exceptions import (
    ManagedSourceStorageUnavailableError,
)
from catalog_service.domain.section import Section
from catalog_service.domain.source import ManagedSource

_LOGGER = logging.getLogger(__name__)


async def synchronize_user_source_tree(
    *,
    storage: SourceStorage,
    user_id: UUID,
    sections: list[Section],
    sources: list[ManagedSource],
) -> None:
    """Синхронизирует visible tree и переводит storage error в domain error."""
    try:
        await storage.synchronize_user_tree(
            user_id=user_id,
            sections=sections,
            sources=sources,
        )
    except SourceStorageError as exc:
        raise ManagedSourceStorageUnavailableError(
            "Managed source directory tree is temporarily unavailable"
        ) from exc


async def restore_user_source_tree_best_effort(
    *,
    storage: SourceStorage,
    user_id: UUID,
    sections: list[Section],
    sources: list[ManagedSource],
) -> None:
    """Best-effort восстанавливает filesystem tree после DB failure."""
    with suppress(SourceStorageError):
        await storage.synchronize_user_tree(
            user_id=user_id,
            sections=sections,
            sources=sources,
        )
        return

    _LOGGER.error(
        "Failed to restore managed source directory tree",
        extra={
            "event": "catalog_source_tree_restore_failed",
            "user_id": str(user_id),
        },
    )
