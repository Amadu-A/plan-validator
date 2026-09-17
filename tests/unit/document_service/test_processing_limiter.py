# tests/unit/document_service/test_processing_limiter.py

"""Unit tests multi-user CPU admission limiter Document Service."""

import asyncio

from document_service.infrastructure.processing_limiter import AsyncSemaphoreProcessingLimiter


def test_processing_limiter_bounds_concurrency() -> None:
    """Semaphore не допускает больше configured CPU-heavy batches одновременно."""

    async def scenario() -> int:
        limiter = AsyncSemaphoreProcessingLimiter(max_concurrent_tasks=2)
        active = 0
        maximum = 0
        lock = asyncio.Lock()

        async def work() -> None:
            nonlocal active, maximum
            async with lock:
                active += 1
                maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            async with lock:
                active -= 1

        await asyncio.gather(*(limiter.run(work) for _ in range(6)))
        return maximum

    assert asyncio.run(scenario()) == 2
