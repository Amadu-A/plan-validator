# services/catalog-service/src/catalog_service/infrastructure/clock.py

"""System UTC Clock implementation Catalog Service."""

from datetime import UTC, datetime


class SystemClock:
    """Возвращает текущее timezone-aware UTC time."""

    def now(self) -> datetime:
        """Возвращает текущее UTC time."""
        return datetime.now(UTC)
