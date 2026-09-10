# tests/unit/embedding_service/test_gpu_lease.py

"""Unit tests cross-process GPU file lease."""

from pathlib import Path

import pytest
from embedding_service.domain.exceptions import EmbeddingGpuLeaseTimeoutError
from embedding_service.infrastructure.gpu_lease import CrossProcessFileGpuLease


def test_gpu_lease_acquire_release(tmp_path: Path) -> None:
    """Проверяет normal acquire/release lifecycle."""
    lease = CrossProcessFileGpuLease(
        path=tmp_path / "gpu.lock",
        poll_seconds=0.01,
    )

    lease.acquire(timeout_seconds=0.1)
    assert lease.acquired is True

    lease.release()
    assert lease.acquired is False


def test_gpu_lease_is_exclusive(tmp_path: Path) -> None:
    """Второй lease не может захватить тот же lock до release первого."""
    path = tmp_path / "gpu.lock"
    first = CrossProcessFileGpuLease(path=path, poll_seconds=0.01)
    second = CrossProcessFileGpuLease(path=path, poll_seconds=0.01)
    first.acquire(timeout_seconds=0.1)

    try:
        with pytest.raises(EmbeddingGpuLeaseTimeoutError):
            second.acquire(timeout_seconds=0.03)
    finally:
        first.release()
        second.release()
