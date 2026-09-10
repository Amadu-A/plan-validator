# services/retrieval-service/src/retrieval_service/application/ports/embedding_gateway.py

"""Application port normalized text embedding RPC."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class EmbeddedTexts:
    """Transport-neutral normalized embedding batch."""

    model: str
    dimension: int
    vectors: tuple[tuple[float, ...], ...]


class EmbeddingGateway(Protocol):
    """Получает GPU embeddings через выделенную expensive queue."""

    async def embed_texts(
        self,
        *,
        texts: tuple[str, ...],
        instruction: str,
        correlation_id: str,
    ) -> EmbeddedTexts:
        """Возвращает normalized vectors для всех texts в исходном порядке."""
