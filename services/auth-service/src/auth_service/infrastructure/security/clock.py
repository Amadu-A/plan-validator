# services/auth-service/src/auth_service/infrastructure/security/clock.py

"""System UTC Clock implementation."""

from datetime import UTC, datetime


class SystemClock:
    """Возвращает текущее timezone-aware UTC time."""

    def now(self) -> datetime:
        """Возвращает текущее время UTC."""
        return datetime.now(UTC)
