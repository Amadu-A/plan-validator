# services/context-service/src/context_service/infrastructure/vector_store/qdrant.py

"""Qdrant adapter temporary per-context T/PZ collections."""

from uuid import NAMESPACE_URL, UUID, uuid5

from qdrant_client import AsyncQdrantClient, models

from context_service.application.ports.vector_store import ContextVectorStore
from context_service.domain.exceptions import ContextVectorStoreError
from context_service.domain.models import (
    ContextSource,
    ContextSourceKind,
    NormalizedContextChunk,
)
from context_service.domain.search import ContextSearchHit, ContextSearchQuery

_SEMANTIC_ROLE = "project_context_non_normative"


class QdrantContextVectorStore(ContextVectorStore):
    """Хранит T и PZ в отдельных временных collections одного context."""

    def __init__(
        self,
        *,
        client: AsyncQdrantClient,
        collection_prefix: str,
        expected_vector_size: int,
    ) -> None:
        """Сохраняет Qdrant client и immutable vector contract."""
        self._client = client
        self._collection_prefix = collection_prefix
        self._expected_vector_size = expected_vector_size

    async def upsert_version(
        self,
        *,
        source: ContextSource,
        fingerprint: str,
        chunks: tuple[NormalizedContextChunk, ...],
        vectors: tuple[tuple[float, ...], ...],
    ) -> None:
        """Idempotent upsert candidate generation в typed collection."""
        if len(chunks) != len(vectors):
            raise ContextVectorStoreError("Chunk/vector batch size mismatch")

        collection_name = self.collection_name(
            context_id=source.context_id,
            kind=source.kind,
        )
        await self._ensure_collection(collection_name)

        points: list[models.PointStruct] = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            if len(vector) != self._expected_vector_size:
                raise ContextVectorStoreError(
                    "Vector dimension does not match Context collection contract"
                )

            payload: dict[str, object] = {
                "user_id": str(source.user_id),
                "context_id": str(source.context_id),
                "source_id": str(source.id),
                "kind": source.kind.value,
                "source_name": source.original_name,
                "source_sha256": source.source_sha256,
                "fingerprint": fingerprint,
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "page_number": chunk.page_number,
                "fragment_index": chunk.fragment_index,
                "heading": chunk.heading,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "semantic_role": _SEMANTIC_ROLE,
            }
            points.append(
                models.PointStruct(
                    id=str(
                        build_context_point_id(
                            source_id=source.id,
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
                collection_name=collection_name,
                points=points,
                wait=True,
            )
        except Exception as exc:
            raise ContextVectorStoreError("Failed to upsert temporary Context vectors") from exc

    async def delete_version(
        self,
        *,
        context_id: UUID,
        kind: ContextSourceKind,
        source_id: UUID,
        fingerprint: str,
    ) -> None:
        """Идемпотентно удаляет candidate/obsolete generation."""
        collection_name = self.collection_name(context_id=context_id, kind=kind)
        if not await self._collection_exists(collection_name):
            return

        await self._delete_by_filter(
            collection_name=collection_name,
            query_filter=models.Filter(
                must=[
                    self._match_value("source_id", str(source_id)),
                    self._match_value("fingerprint", fingerprint),
                ]
            ),
        )

    async def delete_obsolete_versions(
        self,
        *,
        context_id: UUID,
        kind: ContextSourceKind,
        source_id: UUID,
        active_fingerprint: str,
    ) -> None:
        """Удаляет все generations source кроме active fingerprint."""
        collection_name = self.collection_name(context_id=context_id, kind=kind)
        if not await self._collection_exists(collection_name):
            return

        await self._delete_by_filter(
            collection_name=collection_name,
            query_filter=models.Filter(
                must=[self._match_value("source_id", str(source_id))],
                must_not=[self._match_value("fingerprint", active_fingerprint)],
            ),
        )

    async def delete_context(self, *, context_id: UUID) -> None:
        """Идемпотентно удаляет обе collections T и PZ."""
        for kind in ContextSourceKind:
            collection_name = self.collection_name(
                context_id=context_id,
                kind=kind,
            )
            if not await self._collection_exists(collection_name):
                continue
            try:
                await self._client.delete_collection(
                    collection_name=collection_name,
                    timeout=60,
                )
            except Exception as exc:
                raise ContextVectorStoreError(
                    f"Failed to delete Context collection {collection_name}"
                ) from exc

    async def search(
        self,
        *,
        query: ContextSearchQuery,
        source: ContextSource,
        query_vector: tuple[float, ...],
    ) -> tuple[ContextSearchHit, ...]:
        """Ищет только active fingerprint source внутри owner/context/type scope."""
        if source.active_fingerprint is None:
            return ()
        if len(query_vector) != self._expected_vector_size:
            raise ContextVectorStoreError("Context query vector dimension mismatch")

        collection_name = self.collection_name(
            context_id=query.context_id,
            kind=query.kind,
        )
        if not await self._collection_exists(collection_name):
            return ()

        conditions: list[models.FieldCondition] = [
            self._match_value("user_id", str(query.user_id)),
            self._match_value("context_id", str(query.context_id)),
            self._match_value("source_id", str(source.id)),
            self._match_value("kind", query.kind.value),
            self._match_value("fingerprint", source.active_fingerprint),
            self._match_value("semantic_role", _SEMANTIC_ROLE),
        ]

        try:
            response = await self._client.query_points(
                collection_name=collection_name,
                query=list(query_vector),
                query_filter=models.Filter(must=conditions),
                limit=query.limit,
                score_threshold=query.score_threshold,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            raise ContextVectorStoreError("Temporary Context vector search failed") from exc

        return tuple(self._to_search_hit(point) for point in response.points)

    def collection_name(
        self,
        *,
        context_id: UUID,
        kind: ContextSourceKind,
    ) -> str:
        """Строит stable typed temporary collection name без tenant PII."""
        return build_context_collection_name(
            prefix=self._collection_prefix,
            context_id=context_id,
            kind=kind,
        )

    async def _ensure_collection(self, collection_name: str) -> None:
        """Lazy создаёт Cosine collection и выдерживает concurrent create race."""
        if await self._collection_exists(collection_name):
            return

        try:
            await self._client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=self._expected_vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
        except Exception as exc:
            if await self._collection_exists(collection_name):
                return
            raise ContextVectorStoreError(
                f"Failed to create Context collection {collection_name}"
            ) from exc

    async def _collection_exists(self, collection_name: str) -> bool:
        """Проверяет существование collection с единым error mapping."""
        try:
            return bool(await self._client.collection_exists(collection_name))
        except Exception as exc:
            raise ContextVectorStoreError(
                f"Failed to inspect Context collection {collection_name}"
            ) from exc

    async def _delete_by_filter(
        self,
        *,
        collection_name: str,
        query_filter: models.Filter,
    ) -> None:
        """Удаляет temporary points по mandatory exact filter."""
        try:
            await self._client.delete(
                collection_name=collection_name,
                points_selector=models.FilterSelector(filter=query_filter),
                wait=True,
            )
        except Exception as exc:
            raise ContextVectorStoreError("Failed to delete temporary Context vectors") from exc

    @staticmethod
    def _match_value(key: str, value: str) -> models.FieldCondition:
        """Создаёт exact keyword payload condition."""
        return models.FieldCondition(
            key=key,
            match=models.MatchValue(value=value),
        )

    @staticmethod
    def _to_search_hit(point: models.ScoredPoint) -> ContextSearchHit:
        """Преобразует Qdrant payload в explicit non-normative domain hit."""
        payload = point.payload or {}

        try:
            semantic_role = str(payload["semantic_role"])
            if semantic_role != _SEMANTIC_ROLE:
                raise ValueError("Invalid Context semantic role")

            return ContextSearchHit(
                source_id=UUID(str(payload["source_id"])),
                context_id=UUID(str(payload["context_id"])),
                user_id=UUID(str(payload["user_id"])),
                kind=ContextSourceKind(str(payload["kind"])),
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
            raise ContextVectorStoreError(
                "Qdrant point has invalid temporary Context payload"
            ) from exc


def build_context_collection_name(
    *,
    prefix: str,
    context_id: UUID,
    kind: ContextSourceKind,
) -> str:
    """Строит collection name plan_validator_t/pz_<context hex>."""
    normalized_prefix = prefix.strip().lower().replace("-", "_")
    return f"{normalized_prefix}_{kind.value.lower()}_{context_id.hex}"


def build_context_point_id(
    *,
    source_id: UUID,
    fingerprint: str,
    chunk_id: str,
) -> UUID:
    """Строит deterministic UUID point id для idempotent candidate upsert."""
    return uuid5(
        NAMESPACE_URL,
        f"plan-validator-context:{source_id}:{fingerprint}:{chunk_id}",
    )


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


def _optional_int(value: object) -> int | None:
    """Нормализует optional integer payload field."""
    return None if value is None else int(value)


def _optional_str(value: object) -> str | None:
    """Нормализует optional string payload field."""
    return None if value is None else str(value)
