# services/retrieval-service/src/retrieval_service/application/ports/index_job_publisher.py

"""Application port durable normalized source indexing queue."""

from typing import Protocol

from retrieval_service.domain.source_index import IndexSourceJob


class IndexJobPublisher(Protocol):
    """Публикует expensive/reindex source job в bounded CPU/network queue."""

    async def publish(self, job: IndexSourceJob) -> None:
        """Durably публикует indexing command."""
