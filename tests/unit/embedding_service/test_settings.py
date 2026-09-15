# tests/unit/embedding_service/test_settings.py

"""Unit tests Embedding Pydantic Settings."""

from pathlib import Path

import pytest
from embedding_service.core.settings import (
    EmbeddingSettings,
    EmbeddingWorkerSettings,
)
from pydantic import (
    SecretStr,
    ValidationError,
)


def test_embedding_settings_defaults() -> None:
    """Проверяет safe Qwen, queue, cache и bounded admission defaults."""
    settings = EmbeddingSettings(_env_file=None)

    assert settings.service_name == "embedding-service"

    assert settings.embedding_model.name == "Qwen/Qwen3-VL-Embedding-8B"

    assert settings.embedding_model.output_dimension == 4096

    assert settings.embedding_model.hf_home == Path("/models/huggingface")

    assert settings.embedding_model.min_free_vram_gib == 18.0

    assert settings.embedding_model.gpu_lease_path == Path("/var/lock/plan-validator-gpu/gpu.lock")

    assert settings.embedding_model.admission_wait_timeout_seconds == 480.0

    assert settings.embedding_model.gpu_lease_timeout_seconds == 480.0

    assert settings.embedding_queue.name == "plan-validator.gpu.embedding"

    assert settings.embedding_queue.prefetch_count == 1

    assert settings.embedding_queue.rpc_timeout_seconds == 600.0

    assert settings.embedding_queue.graceful_shutdown_seconds == 45


def test_worker_settings_build_encoded_vhost_url() -> None:
    """Проверяет URL encoding project vhost и secret без раскрытия в repr."""
    settings = EmbeddingWorkerSettings(
        rabbitmq_password=SecretStr("unit-test-secret"),
        _env_file=None,
    )

    assert settings.broker_url.endswith("/%2Fplan-validator")

    assert "unit-test-secret" in settings.broker_url

    assert "unit-test-secret" not in repr(settings.rabbitmq_password)


def test_worker_settings_reject_placeholder_password() -> None:
    """Не допускает committed placeholder как реальный RabbitMQ password."""
    with pytest.raises(ValidationError):
        EmbeddingWorkerSettings(
            rabbitmq_password=SecretStr("CHANGE_ME_GENERATED_AUTOMATICALLY"),
            _env_file=None,
        )
