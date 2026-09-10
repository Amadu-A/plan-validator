# tests/unit/embedding_service/test_gpu_runtime.py

"""Unit tests GPU runtime без установки CUDA/Torch dependencies."""

import asyncio
import math
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from embedding_service.core.settings import EmbeddingModelSettings
from embedding_service.domain.embedding import EmbeddingTextInput
from embedding_service.domain.exceptions import EmbeddingVramAdmissionError
from embedding_service.infrastructure import gpu_runtime
from embedding_service.infrastructure.gpu_runtime import QwenEmbeddingRuntime

JOB_ID = UUID("11111111-1111-1111-1111-111111111111")


class FakeCacheProbe:
    """Возвращает заранее заданный local snapshot."""

    def __init__(self, snapshot: Path) -> None:
        """Сохраняет fake snapshot path."""
        self._snapshot = snapshot

    def resolve_snapshot(self) -> Path | None:
        """Возвращает fake snapshot."""
        return self._snapshot


class FakeLease:
    """Фиксирует acquire/release lifecycle."""

    def __init__(self) -> None:
        """Инициализирует counters."""
        self.acquire_count = 0
        self.release_count = 0

    def acquire(self, *, timeout_seconds: float) -> None:
        """Фиксирует acquire вызов."""
        assert timeout_seconds > 0
        self.acquire_count += 1

    def release(self) -> None:
        """Фиксирует release вызов."""
        self.release_count += 1


class FakeVector:
    """Минимальный numpy-like vector для runtime conversion."""

    def __init__(self, values: list[float]) -> None:
        """Сохраняет значения."""
        self._values = values

    def tolist(self) -> list[float]:
        """Возвращает Python list как numpy.ndarray.tolist."""
        return list(self._values)


class FakeCuda:
    """Эмулирует необходимые torch.cuda операции."""

    def __init__(self) -> None:
        """Инициализирует cleanup counters."""
        self.empty_cache_count = 0

    @staticmethod
    def is_available() -> bool:
        """Сообщает, что fake CUDA доступна."""
        return True

    @staticmethod
    def mem_get_info() -> tuple[int, int]:
        """Возвращает достаточно свободной fake VRAM."""
        return 24 * 1024**3, 24 * 1024**3

    @staticmethod
    def reset_peak_memory_stats() -> None:
        """Эмулирует reset peak allocator stats."""

    @staticmethod
    def synchronize() -> None:
        """Эмулирует CUDA synchronize."""

    @staticmethod
    def max_memory_allocated() -> int:
        """Возвращает deterministic peak allocation."""
        return 123456

    def empty_cache(self) -> None:
        """Фиксирует allocator cleanup."""
        self.empty_cache_count += 1

    @staticmethod
    def ipc_collect() -> None:
        """Эмулирует IPC cleanup."""


class FakeModel:
    """SentenceTransformer-like fake successful model."""

    last_init: dict[str, object] | None = None

    def __init__(self, model_path: str, **kwargs: object) -> None:
        """Фиксирует local-only model constructor arguments."""
        type(self).last_init = {
            "model_path": model_path,
            **kwargs,
        }
        self.max_seq_length = 0

    def encode(self, texts: list[str], **kwargs: object) -> list[FakeVector]:
        """Возвращает normalized 64-dimensional fake embedding."""
        assert texts == ["тест требования"]
        assert kwargs["normalize_embeddings"] is True
        value = 1.0 / math.sqrt(64)
        return [FakeVector([value] * 64)]


class FailingFakeModel(FakeModel):
    """SentenceTransformer-like fake с CUDA OOM на inference."""

    def encode(self, texts: list[str], **kwargs: object) -> list[FakeVector]:
        """Эмулирует runtime CUDA OOM."""
        del texts
        del kwargs
        raise RuntimeError("CUDA out of memory")


def _build_fake_torch() -> SimpleNamespace:
    """Создаёт fake torch module с необходимым dtype/CUDA API."""
    return SimpleNamespace(
        bfloat16=object(),
        float16=object(),
        cuda=FakeCuda(),
    )


def test_runtime_loads_local_model_and_releases_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Проверяет полный successful lifecycle без реального GPU."""
    fake_torch = _build_fake_torch()
    fake_sentence_transformers = SimpleNamespace(SentenceTransformer=FakeModel)

    def fake_import(name: str) -> object:
        """Подменяет только тяжёлые runtime modules."""
        if name == "torch":
            return fake_torch
        if name == "sentence_transformers":
            return fake_sentence_transformers
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(gpu_runtime.importlib, "import_module", fake_import)
    monkeypatch.setattr(
        gpu_runtime,
        "_available_system_ram_bytes",
        lambda: 64 * 1024**3,
    )

    lease = FakeLease()
    settings = EmbeddingModelSettings(
        output_dimension=64,
        min_free_ram_gib=1,
        min_free_vram_gib=1,
    )
    runtime = QwenEmbeddingRuntime(
        settings=settings,
        cache_probe=FakeCacheProbe(tmp_path),
        gpu_lease=lease,  # type: ignore[arg-type]
    )

    result = asyncio.run(
        runtime.embed_text(
            job_id=JOB_ID,
            item=EmbeddingTextInput(text="тест требования"),
        )
    )

    assert result.dimension == 64
    assert len(result.vector) == 64
    assert math.isclose(math.sqrt(sum(value**2 for value in result.vector)), 1.0)
    assert result.telemetry.peak_allocated_vram_bytes == 123456
    assert lease.acquire_count == 1
    assert lease.release_count == 1
    assert fake_torch.cuda.empty_cache_count == 1
    assert FakeModel.last_init is not None
    assert FakeModel.last_init["model_path"] == str(tmp_path)
    assert FakeModel.last_init["local_files_only"] is True


def test_runtime_releases_lease_after_cuda_oom(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Проверяет обязательный cleanup при model inference failure."""
    fake_torch = _build_fake_torch()
    fake_sentence_transformers = SimpleNamespace(SentenceTransformer=FailingFakeModel)

    def fake_import(name: str) -> object:
        """Подменяет тяжёлые runtime modules для error path."""
        if name == "torch":
            return fake_torch
        if name == "sentence_transformers":
            return fake_sentence_transformers
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(gpu_runtime.importlib, "import_module", fake_import)
    monkeypatch.setattr(
        gpu_runtime,
        "_available_system_ram_bytes",
        lambda: 64 * 1024**3,
    )

    lease = FakeLease()
    runtime = QwenEmbeddingRuntime(
        settings=EmbeddingModelSettings(
            output_dimension=64,
            min_free_ram_gib=1,
            min_free_vram_gib=1,
        ),
        cache_probe=FakeCacheProbe(tmp_path),
        gpu_lease=lease,  # type: ignore[arg-type]
    )

    with pytest.raises(EmbeddingVramAdmissionError):
        asyncio.run(
            runtime.embed_text(
                job_id=JOB_ID,
                item=EmbeddingTextInput(text="тест требования"),
            )
        )

    assert lease.acquire_count == 1
    assert lease.release_count == 1
    assert fake_torch.cuda.empty_cache_count == 1
