# services/retrieval-service/src/retrieval_service/infrastructure/clock.py

"""System clock adapter Retrieval Service."""

from datetime import UTC, datetime


class SystemClock:
    """Возвращает timezone-aware UTC время операционной системы."""

    def now(self) -> datetime:
        """Возвращает текущее UTC time."""
        return datetime.now(UTC)
