# services/catalog-service/src/catalog_service/application/ports/clock.py

"""Application port источника времени Catalog Service."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Предоставляет timezone-aware текущее время."""

    def now(self) -> datetime:
        """Возвращает текущее UTC time."""
