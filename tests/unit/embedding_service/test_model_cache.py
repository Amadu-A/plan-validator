# tests/unit/embedding_service/test_model_cache.py

"""Unit tests Hugging Face model cache probe."""

from pathlib import Path

from embedding_service.infrastructure.model_cache import HuggingFaceModelCacheProbe

MODEL_NAME = "Qwen/Qwen3-VL-Embedding-8B"


def _create_snapshot(root: Path) -> Path:
    """Создаёт минимальный fake cached snapshot."""
    snapshot = root / "hub" / "models--Qwen--Qwen3-VL-Embedding-8B" / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "modules.json").write_text("[]", encoding="utf-8")
    (snapshot / "model.safetensors.index.json").write_text("{}", encoding="utf-8")
    return snapshot


def test_cache_probe_resolves_huggingface_snapshot(tmp_path: Path) -> None:
    """Находит standard HF_HOME/hub cached snapshot."""
    expected = _create_snapshot(tmp_path)
    probe = HuggingFaceModelCacheProbe(hf_home=tmp_path, model_name=MODEL_NAME)

    assert probe.resolve_snapshot() == expected


def test_cache_probe_rejects_incomplete_snapshot(tmp_path: Path) -> None:
    """Не считает directory готовой без modules/weights metadata."""
    snapshot = tmp_path / "hub" / "models--Qwen--Qwen3-VL-Embedding-8B" / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    probe = HuggingFaceModelCacheProbe(hf_home=tmp_path, model_name=MODEL_NAME)

    assert probe.resolve_snapshot() is None
