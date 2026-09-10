# services/retrieval-service/src/retrieval_service/application/ports/vector_store.py

"""Application port persistent managed-source vector storage."""

from typing import Protocol
from uuid import UUID

from retrieval_service.domain.search import SearchHit, SearchQuery
from retrieval_service.domain.source_index import ManagedSourceIndex, NormalizedChunk


class ManagedSourceVectorStore(Protocol):
    """Хранит immutable fingerprint generations в shared Qdrant corpus."""

    async def upsert_version(
        self,
        *,
        source: ManagedSourceIndex,
        fingerprint: str,
        chunks: tuple[NormalizedChunk, ...],
        vectors: tuple[tuple[float, ...], ...],
    ) -> None:
        """Idempotent upsert candidate source generation."""

    async def delete_version(self, *, source_id: UUID, fingerprint: str) -> None:
        """Идемпотентно удаляет одну candidate/obsolete generation."""

    async def delete_obsolete_versions(
        self,
        *,
        source_id: UUID,
        active_fingerprint: str,
    ) -> None:
        """Удаляет все generations source, кроме active fingerprint."""

    async def delete_source(self, *, source_id: UUID) -> None:
        """Идемпотентно удаляет все vector points managed source."""

    async def search(
        self,
        *,
        query: SearchQuery,
        query_vector: tuple[float, ...],
        active_version_keys: tuple[str, ...],
    ) -> tuple[SearchHit, ...]:
        """Выполняет vector search с mandatory tenant/type/version filters."""

    async def ready(self) -> bool:
        """Проверяет доступность stable managed-source alias без mutation."""
