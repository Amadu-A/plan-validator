# services/document-service/src/document_service/application/ports/processing_limiter.py

"""Bounded CPU admission port Document Service."""

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

T = TypeVar("T")


class ProcessingLimiter(Protocol):
    """Ограничивает одновременные CPU-heavy document operations."""

    async def run(self, operation: Callable[[], Awaitable[T]]) -> T:
        """Выполняет operation после bounded admission."""
