# services/embedding-service/src/embedding_service/infrastructure/model_cache.py

"""Filesystem probe локального Hugging Face cache Qwen embedding model."""

from pathlib import Path


class HuggingFaceModelCacheProbe:
    """Находит complete cached snapshot без обращения к сети."""

    def __init__(self, *, hf_home: Path, model_name: str) -> None:
        """Сохраняет root Hugging Face cache и canonical model identity."""
        self._hf_home = hf_home
        self._model_name = model_name

    def resolve_snapshot(self) -> Path | None:
        """Возвращает локальный snapshot, пригодный для SentenceTransformer."""
        for candidate in self._candidate_snapshots():
            if self._is_complete_snapshot(candidate):
                return candidate

        return None

    def _candidate_snapshots(self) -> tuple[Path, ...]:
        """Строит поддерживаемые Hugging Face cache layouts."""
        owner, separator, model = self._model_name.partition("/")

        if not separator or not owner or not model:
            direct = self._hf_home / self._model_name
            return (direct,)

        cache_directory_name = f"models--{owner}--{model}"
        snapshot_roots = (
            self._hf_home / "hub" / cache_directory_name / "snapshots",
            self._hf_home / cache_directory_name / "snapshots",
        )

        discovered: list[Path] = []

        for snapshots_root in snapshot_roots:
            if not snapshots_root.is_dir():
                continue

            try:
                snapshots = sorted(
                    (path for path in snapshots_root.iterdir() if path.is_dir()),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
            except OSError:
                continue

            discovered.extend(snapshots)

        discovered.extend(
            (
                self._hf_home / owner / model,
                self._hf_home / model,
            )
        )

        return tuple(discovered)

    @staticmethod
    def _is_complete_snapshot(path: Path) -> bool:
        """Проверяет минимальный набор metadata и model weight index/files."""
        if not path.is_dir():
            return False

        required = (
            path / "config.json",
            path / "modules.json",
        )

        if not all(item.is_file() for item in required):
            return False

        weight_index = path / "model.safetensors.index.json"

        if weight_index.is_file():
            return True

        try:
            return any(path.glob("*.safetensors"))
        except OSError:
            return False
