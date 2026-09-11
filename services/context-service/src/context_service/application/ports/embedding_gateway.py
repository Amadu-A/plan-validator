# services/context-service/src/context_service/application/ports/embedding_gateway.py

"""Application port batch embeddings временного Project Context."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class EmbeddedContextTexts:
    """Transport-neutral normalized embedding batch."""

    model: str
    dimension: int
    vectors: tuple[tuple[float, ...], ...]


class ContextEmbeddingGateway(Protocol):
    """Получает embeddings через существующую serialized GPU queue."""

    async def embed_texts(
        self,
        *,
        texts: tuple[str, ...],
        instruction: str,
        correlation_id: str,
    ) -> EmbeddedContextTexts:
        """Возвращает vectors в исходном порядке без GPU dependency в application."""
