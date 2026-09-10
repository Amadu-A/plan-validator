# services/retrieval-service/src/retrieval_service/application/ports/clock.py

"""Application port источника времени Retrieval Service."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Предоставляет timezone-aware текущее время."""

    def now(self) -> datetime:
        """Возвращает текущее UTC time."""
