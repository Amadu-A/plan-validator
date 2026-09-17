# services/document-service/src/document_service/infrastructure/processing_limiter.py

"""In-process bounded CPU admission Document Service."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class AsyncSemaphoreProcessingLimiter:
    """Ограничивает одновременные PDF/OCR batches без broker queue."""

    def __init__(self, max_concurrent_tasks: int) -> None:
        """Создаёт process-local semaphore."""
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)

    async def run(self, operation: Callable[[], Awaitable[T]]) -> T:
        """Ждёт свободный CPU slot и выполняет operation."""
        async with self._semaphore:
            return await operation()
