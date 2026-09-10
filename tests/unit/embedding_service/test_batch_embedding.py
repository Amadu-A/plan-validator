# tests/unit/embedding_service/test_batch_embedding.py

"""Unit tests Stage 9 batch extension Embedding application contract."""

import asyncio
from uuid import UUID

import pytest
from embedding_service.application.use_cases.embed_text import EmbedTextsUseCase
from embedding_service.domain.embedding import (
    EmbeddingBatchResult,
    EmbeddingTelemetry,
    EmbeddingTextInput,
    InvalidEmbeddingInputError,
)

JOB_ID = UUID("11111111-1111-1111-1111-111111111111")


class FakeBatchRuntime:
    """Фиксирует batch items и возвращает deterministic vectors."""

    def __init__(self) -> None:
        """Инициализирует captured items."""
        self.items: tuple[EmbeddingTextInput, ...] = ()

    async def embed_texts(
        self,
        *,
        job_id: UUID,
        items: tuple[EmbeddingTextInput, ...],
    ) -> EmbeddingBatchResult:
        """Возвращает один vector на каждый входной text."""
        self.items = items
        return EmbeddingBatchResult(
            job_id=job_id,
            model="fake-model",
            dimension=2,
            vectors=tuple((0.6, 0.8) for _ in items),
            telemetry=EmbeddingTelemetry(
                available_ram_bytes=1,
                free_vram_before_bytes=2,
                total_vram_bytes=3,
                model_load_ms=4.0,
                encode_ms=5.0,
                total_ms=9.0,
                peak_allocated_vram_bytes=6,
            ),
        )

    async def embed_text(
        self,
        *,
        job_id: UUID,
        item: EmbeddingTextInput,
    ) -> object:
        """Не используется batch use-case и защищает тест от случайного fallback."""
        del job_id
        del item
        raise AssertionError("Batch use-case must call embed_texts")


def test_batch_use_case_uses_one_runtime_call_for_all_texts() -> None:
    """Проверяет preservation порядка и общей instruction внутри одного GPU job."""
    runtime = FakeBatchRuntime()
    use_case = EmbedTextsUseCase(
        runtime=runtime,
        max_text_chars=100,
        max_job_items=4,
    )

    result = asyncio.run(
        use_case.execute(
            job_id=JOB_ID,
            texts=["первый", "второй"],
            instruction="retrieval",
        )
    )

    assert len(result.vectors) == 2
    assert [item.text for item in runtime.items] == ["первый", "второй"]
    assert {item.instruction for item in runtime.items} == {"retrieval"}


def test_batch_use_case_rejects_oversized_job() -> None:
    """Проверяет bounded max_job_items до GPU runtime."""
    use_case = EmbedTextsUseCase(
        runtime=FakeBatchRuntime(),
        max_text_chars=100,
        max_job_items=1,
    )

    with pytest.raises(InvalidEmbeddingInputError):
        asyncio.run(
            use_case.execute(
                job_id=JOB_ID,
                texts=["one", "two"],
            )
        )
