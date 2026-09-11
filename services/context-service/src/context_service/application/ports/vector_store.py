# services/context-service/src/context_service/application/ports/vector_store.py

"""Application port per-context Qdrant storage T/PZ."""

from typing import Protocol
from uuid import UUID

from context_service.domain.models import (
    ContextSource,
    ContextSourceKind,
    NormalizedContextChunk,
)
from context_service.domain.search import ContextSearchHit, ContextSearchQuery


class ContextVectorStore(Protocol):
    """Хранит временные generations T/PZ отдельно от persistent N/U corpus."""

    async def upsert_version(
        self,
        *,
        source: ContextSource,
        fingerprint: str,
        chunks: tuple[NormalizedContextChunk, ...],
        vectors: tuple[tuple[float, ...], ...],
    ) -> None:
        """Idempotent upsert candidate generation source."""

    async def delete_version(
        self,
        *,
        context_id: UUID,
        kind: ContextSourceKind,
        source_id: UUID,
        fingerprint: str,
    ) -> None:
        """Удаляет одну candidate/obsolete generation."""

    async def delete_obsolete_versions(
        self,
        *,
        context_id: UUID,
        kind: ContextSourceKind,
        source_id: UUID,
        active_fingerprint: str,
    ) -> None:
        """Удаляет все generations source кроме active fingerprint."""

    async def delete_context(self, *, context_id: UUID) -> None:
        """Удаляет обе временные T/PZ collections context."""

    async def search(
        self,
        *,
        query: ContextSearchQuery,
        source: ContextSource,
        query_vector: tuple[float, ...],
    ) -> tuple[ContextSearchHit, ...]:
        """Выполняет typed search только по active source generation."""
