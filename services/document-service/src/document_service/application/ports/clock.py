# services/document-service/src/document_service/application/ports/clock.py

"""Clock port Document Service."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Предоставляет UTC time без привязки use-case к system clock."""

    def now(self) -> datetime:
        """Возвращает timezone-aware UTC timestamp."""
