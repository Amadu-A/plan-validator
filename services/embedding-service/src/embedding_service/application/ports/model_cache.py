# services/embedding-service/src/embedding_service/application/ports/model_cache.py

"""Application port локального model cache probe."""

from pathlib import Path
from typing import Protocol


class ModelCacheProbe(Protocol):
    """Проверяет наличие complete local checkpoint без model load."""

    def resolve_snapshot(self) -> Path | None:
        """Возвращает cached snapshot либо None."""
