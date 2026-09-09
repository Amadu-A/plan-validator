# services/auth-service/src/auth_service/application/ports/clock.py

"""Application port источника времени для воспроизводимых use-case tests."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Предоставляет timezone-aware текущее время."""

    def now(self) -> datetime:
        """Возвращает текущее UTC time."""
