# services/embedding-service/src/embedding_service/application/ports/model_runtime.py

"""Application port тяжёлого embedding runtime."""

from typing import Protocol
from uuid import UUID

from embedding_service.domain.embedding import EmbeddingResult, EmbeddingTextInput


class EmbeddingModelRuntime(Protocol):
    """Определяет одну bounded GPU embedding операцию."""

    async def embed_text(
        self,
        *,
        job_id: UUID,
        item: EmbeddingTextInput,
    ) -> EmbeddingResult:
        """Строит normalized embedding и освобождает GPU после job."""
