# services/embedding-service/src/embedding_service/infrastructure/gpu_lease.py

"""Cross-process file lease project GPU Plan Validator."""

import errno
import os
import threading
import time
from pathlib import Path
from typing import BinaryIO

from embedding_service.domain.exceptions import EmbeddingGpuLeaseTimeoutError

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class CrossProcessFileGpuLease:
    """OS advisory lock для сериализации GPU jobs текущего проекта."""

    def __init__(self, *, path: Path, poll_seconds: float) -> None:
        """Сохраняет lock path и polling interval."""
        self._path = path
        self._poll_seconds = poll_seconds
        self._handle: BinaryIO | None = None
        self._state_lock = threading.Lock()

    @property
    def acquired(self) -> bool:
        """Показывает, удерживает ли экземпляр lease."""
        with self._state_lock:
            return self._handle is not None

    def acquire(self, *, timeout_seconds: float) -> None:
        """Выполняет blocking bounded acquire."""
        if self.acquired:
            return

        deadline = time.monotonic() + timeout_seconds
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._path.open("a+b")
        handle.seek(0, os.SEEK_END)

        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()

        while True:
            try:
                self._try_lock(handle)
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                    handle.close()
                    raise

                if time.monotonic() >= deadline:
                    handle.close()
                    raise EmbeddingGpuLeaseTimeoutError(
                        "GPU lease acquisition timeout expired"
                    ) from exc

                time.sleep(self._poll_seconds)
                continue

            with self._state_lock:
                self._handle = handle

            return

    def release(self) -> None:
        """Идемпотентно освобождает OS advisory lock."""
        with self._state_lock:
            handle = self._handle
            self._handle = None

        if handle is None:
            return

        try:
            self._unlock(handle)
        finally:
            handle.close()

    @staticmethod
    def _try_lock(handle: BinaryIO) -> None:
        """Пытается захватить lock без ожидания."""
        handle.seek(0)

        if os.name == "nt":
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock(handle: BinaryIO) -> None:
        """Освобождает ранее захваченный lock."""
        handle.seek(0)

        if os.name == "nt":
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
