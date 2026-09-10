# services/embedding-service/src/embedding_service/application/use_cases/embed_text.py

"""Use-case expensive text embedding через GPU runtime port."""

from uuid import UUID

from plan_validator_common.observability import log_execution_time

from embedding_service.application.ports.model_runtime import EmbeddingModelRuntime
from embedding_service.domain.embedding import EmbeddingResult, EmbeddingTextInput


class EmbedTextUseCase:
    """Валидирует input и делегирует единственную GPU операцию runtime adapter."""

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
