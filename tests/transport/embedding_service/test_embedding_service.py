# tests/transport/embedding_service/test_embedding_service.py

"""Transport tests operational Embedding HTTP API."""

from pathlib import Path

from embedding_service.core.settings import EmbeddingModelSettings, EmbeddingSettings
from embedding_service.transport.app import create_app
from fastapi.testclient import TestClient


def _create_model_cache(root: Path) -> None:
    """Создаёт минимальный ready snapshot для HTTP readiness test."""
    snapshot = root / "hub" / "models--Qwen--Qwen3-VL-Embedding-8B" / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "modules.json").write_text("[]", encoding="utf-8")
    (snapshot / "model.safetensors.index.json").write_text("{}", encoding="utf-8")


def test_embedding_health_and_runtime_contract(tmp_path: Path) -> None:
    """Проверяет liveness/readiness и отсутствие public inference endpoint."""
    _create_model_cache(tmp_path)
    settings = EmbeddingSettings(
        embedding_model=EmbeddingModelSettings(hf_home=tmp_path),
        log_to_file=False,
        _env_file=None,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")
        runtime = client.get("/internal/v1/embedding/runtime")
        forbidden_direct_embed = client.post("/internal/v1/embedding/embed", json={})

    assert live.status_code == 200
    assert live.json()["status"] == "alive"
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert runtime.status_code == 200
    assert runtime.json() == {
        "model": "Qwen/Qwen3-VL-Embedding-8B",
        "dimension": 4096,
        "queue": "plan-validator.gpu.embedding",
        "cache_ready": True,
        "gpu_required": True,
        "offline_only": True,
    }
    assert forbidden_direct_embed.status_code == 404
