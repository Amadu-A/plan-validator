# services/embedding-service/src/embedding_service/application/use_cases/runtime_status.py

"""Use-cases operational model-cache status Embedding Service."""

from dataclasses import dataclass

from embedding_service.application.ports.model_cache import ModelCacheProbe


@dataclass(frozen=True, slots=True)
class EmbeddingRuntimeStatus:
    """Safe operational snapshot без filesystem path и credentials."""

    model: str
    dimension: int
    queue: str
    cache_ready: bool
    gpu_required: bool
    offline_only: bool


class CheckReadinessUseCase:
    """Определяет readiness по наличию complete local model snapshot."""

    def __init__(self, cache_probe: ModelCacheProbe) -> None:
        """Сохраняет model cache probe."""
        self._cache_probe = cache_probe

    async def execute(self) -> bool:
        """Возвращает True только для найденного complete snapshot."""
        return self._cache_probe.resolve_snapshot() is not None


class GetRuntimeStatusUseCase:
    """Возвращает safe runtime contract для внутренних сервисов."""

    def __init__(
        self,
        *,
        model: str,
        dimension: int,
        queue: str,
        cache_probe: ModelCacheProbe,
    ) -> None:
        """Сохраняет primitive application data и cache probe."""
        self._model = model
        self._dimension = dimension
        self._queue = queue
        self._cache_probe = cache_probe

    async def execute(self) -> EmbeddingRuntimeStatus:
        """Формирует status без загрузки CUDA/model runtime."""
        return EmbeddingRuntimeStatus(
            model=self._model,
            dimension=self._dimension,
            queue=self._queue,
            cache_ready=self._cache_probe.resolve_snapshot() is not None,
            gpu_required=True,
            offline_only=True,
        )
