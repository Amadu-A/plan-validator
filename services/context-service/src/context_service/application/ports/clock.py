# services/context-service/src/context_service/application/ports/clock.py

"""Application clock port Context Service."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Предоставляет timezone-aware application time."""

    def now(self) -> datetime:
        """Возвращает текущий UTC timestamp."""
