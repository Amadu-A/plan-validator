# services/embedding-service/src/embedding_service/infrastructure/gpu_runtime.py

"""Lazy one-job GPU runtime Qwen/Qwen3-VL-Embedding-8B."""

import asyncio
import gc
import importlib
import logging
import os
import time
from contextlib import suppress
from pathlib import Path
from uuid import UUID

from embedding_service.application.ports.model_cache import ModelCacheProbe
from embedding_service.core.settings import EmbeddingModelSettings
from embedding_service.domain.embedding import (
    EmbeddingBatchResult,
    EmbeddingResult,
    EmbeddingTelemetry,
    EmbeddingTextInput,
)
from embedding_service.domain.exceptions import (
    EmbeddingModelCacheError,
    EmbeddingModelExecutionError,
    EmbeddingRamAdmissionError,
    EmbeddingRuntimeError,
    EmbeddingVramAdmissionError,
)
from embedding_service.infrastructure.gpu_lease import CrossProcessFileGpuLease

_LOGGER = logging.getLogger(__name__)
_CGROUP_UNLIMITED_THRESHOLD = 1 << 60


class QwenEmbeddingRuntime:
    """Загружает checkpoint только внутри lease и освобождает его после job."""

    def __init__(
        self,
        *,
        settings: EmbeddingModelSettings,
        cache_probe: ModelCacheProbe,
        gpu_lease: CrossProcessFileGpuLease | None = None,
    ) -> None:
        """Сохраняет bounded runtime dependencies."""
        self._settings = settings
        self._cache_probe = cache_probe
        self._gpu_lease = gpu_lease or CrossProcessFileGpuLease(
            path=settings.gpu_lease_path,
            poll_seconds=settings.gpu_lease_poll_seconds,
        )
        self._semaphore = asyncio.Semaphore(1)

    async def embed_text(
        self,
        *,
        job_id: UUID,
        item: EmbeddingTextInput,
    ) -> EmbeddingResult:
        """Выполняет одну serialized GPU operation вне event loop."""
        batch = await self.embed_texts(job_id=job_id, items=(item,))

        return EmbeddingResult(
            job_id=batch.job_id,
            model=batch.model,
            dimension=batch.dimension,
            vector=batch.vectors[0],
            telemetry=batch.telemetry,
        )

    async def embed_texts(
        self,
        *,
        job_id: UUID,
        items: tuple[EmbeddingTextInput, ...],
    ) -> EmbeddingBatchResult:
        """Выполняет batch inference за один lease/model-load lifecycle."""
        async with self._semaphore:
            return await asyncio.to_thread(self._embed_texts_sync, job_id, items)

    def _embed_texts_sync(
        self,
        job_id: UUID,
        items: tuple[EmbeddingTextInput, ...],
    ) -> EmbeddingBatchResult:
        """Выполняет lease → admission → load → batch infer → unload lifecycle."""
        if not items:
            raise EmbeddingModelExecutionError("Embedding runtime received empty batch")

        if len(items) > self._settings.max_job_items:
            raise EmbeddingModelExecutionError(
                f"Embedding runtime batch exceeds {self._settings.max_job_items} items"
            )

        instructions = {
            item.instruction.strip() if item.instruction is not None else None for item in items
        }

        if len(instructions) != 1:
            raise EmbeddingModelExecutionError(
                "All texts in one embedding GPU job must use the same instruction"
            )

        started_at = time.perf_counter()
        snapshot = self._cache_probe.resolve_snapshot()

        if snapshot is None:
            raise EmbeddingModelCacheError(
                f"Cached model snapshot is missing for {self._settings.name}"
            )

        self._gpu_lease.acquire(timeout_seconds=self._settings.gpu_lease_timeout_seconds)
        torch: object | None = None
        model: object | None = None

        try:
            available_ram_bytes = _require_system_ram(
                required_bytes=self._settings.min_free_ram_bytes
            )
            torch = importlib.import_module("torch")
            free_vram_bytes, total_vram_bytes = self._wait_for_vram(torch)
            torch.cuda.reset_peak_memory_stats()

            model_started_at = time.perf_counter()
            sentence_transformers = importlib.import_module("sentence_transformers")
            model_class = sentence_transformers.SentenceTransformer
            model_dtype = getattr(torch, self._settings.dtype)

            _LOGGER.info(
                "Qwen embedding model load started",
                extra={
                    "event": "embedding_model_load_started",
                    "model": self._settings.name,
                    "dimension": self._settings.output_dimension,
                    "item_count": len(items),
                    "available_ram_bytes": available_ram_bytes,
                    "free_vram_bytes": free_vram_bytes,
                    "total_vram_bytes": total_vram_bytes,
                },
            )

            model = model_class(
                str(snapshot),
                local_files_only=True,
                model_kwargs={
                    "torch_dtype": model_dtype,
                    "device_map": "cuda:0",
                    "low_cpu_mem_usage": True,
                },
            )
            model.max_seq_length = self._settings.max_input_tokens
            _cuda_synchronize(torch)
            model_load_ms = _duration_ms(model_started_at)

            encode_started_at = time.perf_counter()
            encode_kwargs: dict[str, object] = {
                "batch_size": self._settings.max_batch_size,
                "convert_to_numpy": True,
                "normalize_embeddings": True,
                "show_progress_bar": False,
                "truncate_dim": self._settings.output_dimension,
            }
            instruction = next(iter(instructions))

            if instruction:
                encode_kwargs["prompt"] = instruction

            embeddings = model.encode(
                [item.text.strip() for item in items],
                **encode_kwargs,
            )
            _cuda_synchronize(torch)
            encode_ms = _duration_ms(encode_started_at)

            if len(embeddings) != len(items):
                raise EmbeddingModelExecutionError("Embedding runtime returned invalid batch size")

            vectors = tuple(
                tuple(float(value) for value in embedding.tolist()) for embedding in embeddings
            )

            if any(len(vector) != self._settings.output_dimension for vector in vectors):
                raise EmbeddingModelExecutionError(
                    "Embedding dimension does not match configured dimension"
                )

            telemetry = EmbeddingTelemetry(
                available_ram_bytes=available_ram_bytes,
                free_vram_before_bytes=free_vram_bytes,
                total_vram_bytes=total_vram_bytes,
                model_load_ms=model_load_ms,
                encode_ms=encode_ms,
                total_ms=_duration_ms(started_at),
                peak_allocated_vram_bytes=int(torch.cuda.max_memory_allocated()),
            )

            _LOGGER.info(
                "Qwen embedding completed",
                extra={
                    "event": "embedding_completed",
                    "job_id": str(job_id),
                    "model": self._settings.name,
                    "dimension": self._settings.output_dimension,
                    "item_count": len(vectors),
                    "model_load_ms": telemetry.model_load_ms,
                    "encode_ms": telemetry.encode_ms,
                    "total_ms": telemetry.total_ms,
                    "peak_allocated_vram_bytes": telemetry.peak_allocated_vram_bytes,
                },
            )

            return EmbeddingBatchResult(
                job_id=job_id,
                model=self._settings.name,
                dimension=self._settings.output_dimension,
                vectors=vectors,
                telemetry=telemetry,
            )
        except EmbeddingRuntimeError:
            raise
        except MemoryError as exc:
            raise EmbeddingRamAdmissionError("System RAM exhausted during model execution") from exc
        except RuntimeError as exc:
            lowered = str(exc).casefold()

            if "out of memory" in lowered or ("cuda" in lowered and "memory" in lowered):
                raise EmbeddingVramAdmissionError("CUDA out of memory during embedding") from exc

            raise EmbeddingModelExecutionError(
                f"Embedding runtime failed: {type(exc).__name__}: {exc}"
            ) from exc
        except Exception as exc:
            raise EmbeddingModelExecutionError(
                f"Embedding runtime failed: {type(exc).__name__}: {exc}"
            ) from exc
        finally:
            model = None
            gc.collect()
            _release_cuda_cache(torch)
            self._gpu_lease.release()

    def _wait_for_vram(self, torch: object) -> tuple[int, int]:
        """Ждёт required free VRAM bounded-временем после получения lease."""
        if not torch.cuda.is_available():
            raise EmbeddingVramAdmissionError("CUDA is not available inside embedding worker")

        deadline = time.monotonic() + self._settings.admission_wait_timeout_seconds

        while True:
            free_vram, total_vram = torch.cuda.mem_get_info()
            free_vram_bytes = int(free_vram)
            total_vram_bytes = int(total_vram)

            if free_vram_bytes >= self._settings.min_free_vram_bytes:
                return free_vram_bytes, total_vram_bytes

            if time.monotonic() >= deadline:
                raise EmbeddingVramAdmissionError(
                    "VRAM admission timeout expired: "
                    f"free={free_vram_bytes}, required={self._settings.min_free_vram_bytes}"
                )

            _LOGGER.info(
                "Waiting for free VRAM",
                extra={
                    "event": "embedding_vram_wait",
                    "free_vram_bytes": free_vram_bytes,
                    "required_vram_bytes": self._settings.min_free_vram_bytes,
                },
            )
            time.sleep(self._settings.admission_poll_seconds)


def _duration_ms(started_at: float) -> float:
    """Возвращает rounded operation duration в milliseconds."""
    return round((time.perf_counter() - started_at) * 1000, 3)


def _read_integer_file(path: Path) -> int | None:
    """Best-effort читает non-negative integer из procfs/cgroup."""
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    if not value or value == "max":
        return None

    try:
        parsed = int(value)
    except ValueError:
        return None

    return parsed if parsed >= 0 else None


def _linux_mem_available_bytes() -> int | None:
    """Возвращает Linux MemAvailable из /proc/meminfo."""
    path = Path("/proc/meminfo")

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None

    for line in content.splitlines():
        if not line.startswith("MemAvailable:"):
            continue

        parts = line.split()

        if len(parts) < 2:
            return None

        try:
            return int(parts[1]) * 1024
        except ValueError:
            return None

    return None


def _sysconf_available_ram_bytes() -> int | None:
    """Возвращает free RAM через POSIX sysconf как fallback."""
    sysconf = getattr(os, "sysconf", None)

    if not callable(sysconf):
        return None

    try:
        pages = int(sysconf("SC_AVPHYS_PAGES"))
        page_size = int(sysconf("SC_PAGE_SIZE"))
    except (OSError, TypeError, ValueError):
        return None

    if pages <= 0 or page_size <= 0:
        return None

    return pages * page_size


def _cgroup_available_ram_bytes() -> int | None:
    """Возвращает доступную RAM для cgroup v2/v1 при bounded limit."""
    candidates = (
        (
            Path("/sys/fs/cgroup/memory.max"),
            Path("/sys/fs/cgroup/memory.current"),
        ),
        (
            Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
            Path("/sys/fs/cgroup/memory/memory.usage_in_bytes"),
        ),
    )

    for limit_path, current_path in candidates:
        limit = _read_integer_file(limit_path)
        current = _read_integer_file(current_path)

        if limit is None or current is None or limit >= _CGROUP_UNLIMITED_THRESHOLD:
            continue

        return max(limit - current, 0)

    return None


def _available_system_ram_bytes() -> int | None:
    """Возвращает minimum host/cgroup available RAM."""
    host_available = _linux_mem_available_bytes() or _sysconf_available_ram_bytes()
    cgroup_available = _cgroup_available_ram_bytes()
    candidates = [value for value in (host_available, cgroup_available) if value is not None]

    return min(candidates) if candidates else None


def _require_system_ram(*, required_bytes: int) -> int:
    """Fail-closed проверяет free system RAM перед import тяжёлой модели."""
    available = _available_system_ram_bytes()

    if available is None:
        raise EmbeddingRamAdmissionError("Unable to determine available system RAM")

    if available < required_bytes:
        raise EmbeddingRamAdmissionError(
            f"Insufficient free RAM: available={available}, required={required_bytes}"
        )

    return available


def _cuda_synchronize(torch: object) -> None:
    """Синхронизирует CUDA stream для корректной telemetry при наличии метода."""
    synchronize = getattr(torch.cuda, "synchronize", None)

    if callable(synchronize):
        synchronize()


def _release_cuda_cache(torch: object | None) -> None:
    """Best-effort освобождает allocator cache после уничтожения checkpoint."""
    if torch is None:
        return

    cuda = getattr(torch, "cuda", None)

    if cuda is None:
        return

    is_available = getattr(cuda, "is_available", None)

    if not callable(is_available) or not is_available():
        return

    empty_cache = getattr(cuda, "empty_cache", None)

    if callable(empty_cache):
        empty_cache()

    ipc_collect = getattr(cuda, "ipc_collect", None)

    if callable(ipc_collect):
        with suppress(RuntimeError):
            ipc_collect()
