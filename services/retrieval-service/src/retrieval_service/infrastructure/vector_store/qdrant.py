# services/retrieval-service/src/retrieval_service/infrastructure/vector_store/qdrant.py

"""Qdrant adapter shared persistent N/U managed-source corpus."""

from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from retrieval_service.application.ports.vector_store import ManagedSourceVectorStore
from retrieval_service.domain.exceptions import RetrievalVectorStoreError
from retrieval_service.domain.search import SearchHit, SearchQuery
from retrieval_service.domain.source_index import (
    ManagedSourceIndex,
    NormalizedChunk,
    SourceKind,
    build_point_id,
    build_version_key,
)


class QdrantManagedSourceVectorStore(ManagedSourceVectorStore):
    """Хранит immutable generations одной shared collection за stable alias."""

    def __init__(
        self,
        *,
        client: AsyncQdrantClient,
        alias_name: str,
        expected_vector_size: int,
    ) -> None:
        """Сохраняет Qdrant client, stable alias и dimension contract."""
        self._client = client
        self._alias_name = alias_name
        self._expected_vector_size = expected_vector_size

    async def upsert_version(
        self,
        *,
        source: ManagedSourceIndex,
        fingerprint: str,
        chunks: tuple[NormalizedChunk, ...],
        vectors: tuple[tuple[float, ...], ...],
    ) -> None:
        """Idempotent upsert candidate source generation."""
        if len(chunks) != len(vectors):
            raise RetrievalVectorStoreError("Chunk/vector batch size mismatch")

        points: list[models.PointStruct] = []
        version_key = build_version_key(
            source_id=source.source_id,
            fingerprint=fingerprint,
        )

        for chunk, vector in zip(chunks, vectors, strict=True):
            if len(vector) != self._expected_vector_size:
                raise RetrievalVectorStoreError(
                    "Vector dimension does not match Qdrant collection contract"
                )

            payload: dict[str, object] = {
                "user_id": str(source.user_id),
                "kind": source.kind.value,
                "section_id": str(source.section_id),
                "source_id": str(source.source_id),
                "source_name": source.original_name,
                "source_sha256": source.source_sha256,
                "fingerprint": fingerprint,
                "version_key": version_key,
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "page_number": chunk.page_number,
                "fragment_index": chunk.fragment_index,
                "heading": chunk.heading,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
            }
            points.append(
                models.PointStruct(
                    id=str(
                        build_point_id(
                            source_id=source.source_id,
                            fingerprint=fingerprint,
                            chunk_id=chunk.chunk_id,
                        )
                    ),
                    vector=list(vector),
                    payload=payload,
                )
            )

        try:
            await self._client.upsert(
                collection_name=self._alias_name,
                points=points,
                wait=True,
            )
        except Exception as exc:
            raise RetrievalVectorStoreError("Failed to upsert managed-source vectors") from exc

    async def delete_version(self, *, source_id: UUID, fingerprint: str) -> None:
        """Идемпотентно удаляет одну candidate/obsolete generation."""
        await self._delete_by_filter(
            models.Filter(
                must=[
                    self._match_value("source_id", str(source_id)),
                    self._match_value("fingerprint", fingerprint),
                ]
            )
        )

    async def delete_obsolete_versions(
        self,
        *,
        source_id: UUID,
        active_fingerprint: str,
    ) -> None:
        """Удаляет все generations source, кроме active fingerprint."""
        await self._delete_by_filter(
            models.Filter(
                must=[self._match_value("source_id", str(source_id))],
                must_not=[self._match_value("fingerprint", active_fingerprint)],
            )
        )

    async def delete_source(self, *, source_id: UUID) -> None:
        """Идемпотентно удаляет все vector points managed source."""
        await self._delete_by_filter(
            models.Filter(must=[self._match_value("source_id", str(source_id))])
        )

    async def search(
        self,
        *,
        query: SearchQuery,
        query_vector: tuple[float, ...],
        active_version_keys: tuple[str, ...],
    ) -> tuple[SearchHit, ...]:
        """Выполняет vector search с tenant/type/version и exact filters."""
        if not active_version_keys:
            return ()

        if len(query_vector) != self._expected_vector_size:
            raise RetrievalVectorStoreError("Query vector dimension mismatch")

        conditions: list[models.FieldCondition] = [
            self._match_value("user_id", str(query.user_id)),
            self._match_value("kind", query.kind.value),
            models.FieldCondition(
                key="version_key",
                match=models.MatchAny(any=list(active_version_keys)),
            ),
        ]

        if query.section_ids:
            conditions.append(
                models.FieldCondition(
                    key="section_id",
                    match=models.MatchAny(any=[str(value) for value in query.section_ids]),
                )
            )

        if query.source_ids:
            conditions.append(
                models.FieldCondition(
                    key="source_id",
                    match=models.MatchAny(any=[str(value) for value in query.source_ids]),
                )
            )

        try:
            response = await self._client.query_points(
                collection_name=self._alias_name,
                query=list(query_vector),
                query_filter=models.Filter(must=conditions),
                limit=query.limit,
                score_threshold=query.score_threshold,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            raise RetrievalVectorStoreError("Managed-source vector search failed") from exc

        return tuple(self._to_search_hit(point) for point in response.points)

    async def ready(self) -> bool:
        """Проверяет stable alias и expected vector dimension без mutation."""
        try:
            info = await self._client.get_collection(self._alias_name)
        except Exception:
            return False

        vectors = info.config.params.vectors
        vector_size = getattr(vectors, "size", None)

        return vector_size == self._expected_vector_size

    async def _delete_by_filter(self, query_filter: models.Filter) -> None:
        """Удаляет Qdrant points по mandatory payload filter."""
        try:
            await self._client.delete(
                collection_name=self._alias_name,
                points_selector=models.FilterSelector(filter=query_filter),
                wait=True,
            )
        except Exception as exc:
            raise RetrievalVectorStoreError("Failed to delete managed-source vectors") from exc

    @staticmethod
    def _match_value(
        key: str,
        value: str,
    ) -> models.FieldCondition:
        """Создаёт exact keyword condition."""
        return models.FieldCondition(
            key=key,
            match=models.MatchValue(value=value),
        )

    @staticmethod
    def _to_search_hit(
        point: models.ScoredPoint,
    ) -> SearchHit:
        """Преобразует Qdrant ScoredPoint payload в typed domain hit."""
        payload = point.payload or {}

        try:
            return SearchHit(
                source_id=UUID(str(payload["source_id"])),
                user_id=UUID(str(payload["user_id"])),
                section_id=UUID(str(payload["section_id"])),
                kind=SourceKind(str(payload["kind"])),
                source_name=str(payload["source_name"]),
                chunk_id=str(payload["chunk_id"]),
                text=str(payload["text"]),
                score=float(point.score),
                fingerprint=str(payload["fingerprint"]),
                page_number=_optional_int(payload.get("page_number")),
                fragment_index=_optional_int(payload.get("fragment_index")),
                heading=_optional_str(payload.get("heading")),
                char_start=_optional_int(payload.get("char_start")),
                char_end=_optional_int(payload.get("char_end")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RetrievalVectorStoreError(
                "Qdrant point has invalid managed-source payload"
            ) from exc


def _optional_int(value: object) -> int | None:
    """Нормализует optional integer payload field."""
    return None if value is None else int(value)


def _optional_str(value: object) -> str | None:
    """Нормализует optional string payload field."""
    return None if value is None else str(value)


def build_qdrant_client(
    *,
    host: str,
    http_port: int,
    grpc_port: int,
    prefer_grpc: bool,
    timeout_seconds: float,
) -> AsyncQdrantClient:
    """Создаёт bounded async Qdrant client."""
    return AsyncQdrantClient(
        host=host,
        port=http_port,
        grpc_port=grpc_port,
        prefer_grpc=prefer_grpc,
        timeout=timeout_seconds,
    )
