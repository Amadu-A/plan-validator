# services/context-service/src/context_service/infrastructure/clock.py

"""System clock Context Service."""

from datetime import UTC, datetime


class SystemClock:
    """Возвращает timezone-aware UTC application time."""

    def now(self) -> datetime:
        """Возвращает текущий UTC timestamp."""
        return datetime.now(UTC)
