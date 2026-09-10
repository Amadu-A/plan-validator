# services/retrieval-service/src/retrieval_service/infrastructure/messaging/index_job_publisher.py

"""RabbitMQ publisher normalized managed-source indexing jobs."""

from aio_pika import DeliveryMode, Message

from retrieval_service.application.ports.index_job_publisher import IndexJobPublisher
from retrieval_service.core.settings import RetrievalSettings
from retrieval_service.domain.exceptions import RetrievalDependencyError
from retrieval_service.domain.source_index import IndexSourceJob
from retrieval_service.infrastructure.messaging.rabbitmq import connect_retrieval_broker
from retrieval_service.infrastructure.messaging.schemas import (
    NormalizedChunkMessage,
    SourceIndexJobMessage,
)


class RabbitIndexJobPublisher(IndexJobPublisher):
    """Durably публикует normalized indexing commands в dedicated queue."""

    def __init__(self, settings: RetrievalSettings) -> None:
        """Сохраняет immutable RabbitMQ settings."""
        self._settings = settings

    async def publish(self, job: IndexSourceJob) -> None:
        """Публикует job через default exchange после passive queue validation."""
        message = SourceIndexJobMessage(
            job_id=job.job_id,
            source_id=job.source_id,
            source_sha256=job.source_sha256,
            correlation_id=job.correlation_id,
            chunks=[
                NormalizedChunkMessage(
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    page_number=chunk.page_number,
                    fragment_index=chunk.fragment_index,
                    heading=chunk.heading,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                )
                for chunk in job.chunks
            ],
        )
        connection = await connect_retrieval_broker(self._settings)

        try:
            channel = await connection.channel(
                publisher_confirms=True,
                on_return_raises=True,
            )
            await channel.declare_queue(
                self._settings.retrieval_queues.index_queue_name,
                passive=True,
            )
            await channel.default_exchange.publish(
                Message(
                    body=message.model_dump_json().encode("utf-8"),
                    content_type="application/json",
                    content_encoding="utf-8",
                    message_id=str(job.job_id),
                    correlation_id=job.correlation_id,
                    delivery_mode=DeliveryMode.PERSISTENT,
                ),
                routing_key=self._settings.retrieval_queues.index_queue_name,
                mandatory=True,
            )
        except Exception as exc:
            raise RetrievalDependencyError("Failed to enqueue source indexing job") from exc
        finally:
            await connection.close()
