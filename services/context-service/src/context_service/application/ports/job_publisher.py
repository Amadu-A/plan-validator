# services/context-service/src/context_service/application/ports/job_publisher.py

"""Application port durable Context indexing queue."""

from typing import Protocol
from uuid import UUID


class ContextIndexJobPublisher(Protocol):
    """Публикует только identifier persistent indexing job."""

    async def publish(
        self,
        *,
        job_id: UUID,
        correlation_id: str,
    ) -> None:
        """Публикует recoverable command либо поднимает dependency error."""
