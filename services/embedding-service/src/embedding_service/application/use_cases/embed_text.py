# services/embedding-service/src/embedding_service/application/use_cases/embed_text.py

"""Use-cases expensive text embedding через GPU runtime port."""

from uuid import UUID

from plan_validator_common.observability import log_execution_time

from embedding_service.application.ports.model_runtime import EmbeddingModelRuntime
from embedding_service.domain.embedding import (
    EmbeddingBatchResult,
    EmbeddingResult,
    EmbeddingTextInput,
    InvalidEmbeddingInputError,
)


class EmbedTextUseCase:
    """Валидирует один input и делегирует GPU operation runtime adapter."""

    def __init__(self, *, runtime: EmbeddingModelRuntime, max_text_chars: int) -> None:
        """Сохраняет application dependencies и bounded input limit."""
        self._runtime = runtime
        self._max_text_chars = max_text_chars

    @log_execution_time("embedding.embed_text")
    async def execute(
        self,
        *,
        job_id: UUID,
        text: str,
        instruction: str | None = None,
    ) -> EmbeddingResult:
        """Строит embedding после domain validation."""
        item = EmbeddingTextInput(text=text, instruction=instruction)
        item.validate(max_text_chars=self._max_text_chars)

        return await self._runtime.embed_text(job_id=job_id, item=item)


class EmbedTextsUseCase:
    """Валидирует batch и сохраняет одну загрузку модели на весь GPU job."""

    def __init__(
        self,
        *,
        runtime: EmbeddingModelRuntime,
        max_text_chars: int,
        max_job_items: int,
    ) -> None:
        """Сохраняет runtime и ограничения batch request."""
        self._runtime = runtime
        self._max_text_chars = max_text_chars
        self._max_job_items = max_job_items

    @log_execution_time("embedding.embed_texts")
    async def execute(
        self,
        *,
        job_id: UUID,
        texts: list[str],
        instruction: str | None = None,
    ) -> EmbeddingBatchResult:
        """Строит normalized vectors для bounded списка текстов."""
        if not texts:
            raise InvalidEmbeddingInputError("Embedding batch must not be empty")

        if len(texts) > self._max_job_items:
            raise InvalidEmbeddingInputError(
                f"Embedding batch exceeds {self._max_job_items} item limit"
            )

        items = tuple(EmbeddingTextInput(text=text, instruction=instruction) for text in texts)

        for item in items:
            item.validate(max_text_chars=self._max_text_chars)

        return await self._runtime.embed_texts(job_id=job_id, items=items)
