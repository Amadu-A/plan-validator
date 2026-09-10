# services/embedding-service/src/embedding_service/application/ports/model_runtime.py

"""Application port тяжёлого embedding runtime."""

from typing import Protocol
from uuid import UUID

from embedding_service.domain.embedding import (
    EmbeddingBatchResult,
    EmbeddingResult,
    EmbeddingTextInput,
)


class EmbeddingModelRuntime(Protocol):
    """Определяет bounded single/batch GPU embedding операции."""

    async def embed_text(
        self,
        *,
        job_id: UUID,
        item: EmbeddingTextInput,
    ) -> EmbeddingResult:
        """Строит один normalized embedding и освобождает GPU после job."""

    async def embed_texts(
        self,
        *,
        job_id: UUID,
        items: tuple[EmbeddingTextInput, ...],
    ) -> EmbeddingBatchResult:
        """Строит несколько embeddings за один model-load lifecycle."""
