# services/document-service/src/document_service/infrastructure/clock.py

"""System UTC clock adapter."""

from datetime import UTC, datetime


class SystemClock:
    """Возвращает timezone-aware UTC time."""

    def now(self) -> datetime:
        """Возвращает текущий UTC timestamp."""
        return datetime.now(UTC)
