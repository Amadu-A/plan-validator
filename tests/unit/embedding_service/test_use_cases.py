# tests/unit/embedding_service/test_use_cases.py

"""Unit tests Embedding application use-cases."""

import asyncio
from pathlib import Path
from uuid import UUID

import pytest
from embedding_service.application.use_cases.embed_text import EmbedTextUseCase
from embedding_service.application.use_cases.runtime_status import (
    CheckReadinessUseCase,
    GetRuntimeStatusUseCase,
)
from embedding_service.core.settings import EmbeddingModelSettings, EmbeddingSettings
from embedding_service.domain.embedding import (
    EmbeddingResult,
    EmbeddingTelemetry,
    EmbeddingTextInput,
    InvalidEmbeddingInputError,
)

JOB_ID = UUID("11111111-1111-1111-1111-111111111111")


class FakeRuntime:
    """Возвращает deterministic tiny vector без GPU dependencies."""

    async def embed_text(
        self,
        *,
        job_id: UUID,
        item: EmbeddingTextInput,
    ) -> EmbeddingResult:
        """Возвращает successful fake result."""
        del item
        return EmbeddingResult(
            job_id=job_id,
            model="fake",
            dimension=2,
            vector=(0.6, 0.8),
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


class FakeCacheProbe:
    """Configurable fake local cache probe."""

    def __init__(self, path: Path | None) -> None:
        """Сохраняет возвращаемый snapshot path."""
        self._path = path

    def resolve_snapshot(self) -> Path | None:
        """Возвращает configured path."""
        return self._path


def test_embed_use_case_validates_and_delegates() -> None:
    """Проверяет application boundary без framework/GPU coupling."""
    use_case = EmbedTextUseCase(runtime=FakeRuntime(), max_text_chars=100)
    result = asyncio.run(use_case.execute(job_id=JOB_ID, text="нормативное требование"))

    assert result.job_id == JOB_ID
    assert result.vector == (0.6, 0.8)


def test_embed_use_case_rejects_empty_text() -> None:
    """Проверяет domain validation пустого текста."""
    use_case = EmbedTextUseCase(runtime=FakeRuntime(), max_text_chars=100)

    with pytest.raises(InvalidEmbeddingInputError):
        asyncio.run(use_case.execute(job_id=JOB_ID, text="   "))


def test_runtime_status_reports_cache_without_loading_model(tmp_path: Path) -> None:
    """Проверяет readiness/status contract независимо от CUDA runtime."""
    settings = EmbeddingSettings(
        embedding_model=EmbeddingModelSettings(hf_home=tmp_path),
        _env_file=None,
    )
    probe = FakeCacheProbe(tmp_path / "snapshot")

    assert asyncio.run(CheckReadinessUseCase(probe).execute()) is True

    status = asyncio.run(
        GetRuntimeStatusUseCase(
            model=settings.embedding_model.name,
            dimension=settings.embedding_model.output_dimension,
            queue=settings.embedding_queue.name,
            cache_probe=probe,
        ).execute()
    )
    assert status.model == "Qwen/Qwen3-VL-Embedding-8B"
    assert status.dimension == 4096
    assert status.queue == "plan-validator.gpu.embedding"
    assert status.cache_ready is True
    assert status.offline_only is True
