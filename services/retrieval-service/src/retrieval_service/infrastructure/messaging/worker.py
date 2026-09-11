# services/retrieval-service/src/retrieval_service/infrastructure/messaging/worker.py

"""RabbitMQ consumers Catalog lifecycle events и normalized indexing jobs."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from aio_pika import ExchangeType
from aio_pika.abc import AbstractIncomingMessage
from plan_validator_common.observability import (
    configure_logging,
    scoped_log_context,
)
from pydantic import ValidationError

from retrieval_service.application.use_cases.catalog_events import (
    DeleteCatalogSourceUseCase,
    RegisterCatalogSourceUseCase,
)
from retrieval_service.application.use_cases.index_source import (
    IndexManagedSourceUseCase,
)
from retrieval_service.core.settings import (
    RetrievalWorkerSettings,
    load_retrieval_worker_settings,
)
from retrieval_service.domain.exceptions import (
    RetrievalDependencyError,
    RetrievalSourceConflictError,
    RetrievalSourceNotFoundError,
    RetrievalValidationError,
)
from retrieval_service.domain.source_index import (
    IndexSourceJob,
    NormalizedChunk,
    SourceKind,
)
from retrieval_service.infrastructure.clock import SystemClock
from retrieval_service.infrastructure.database.engine import (
    create_retrieval_engine,
    create_retrieval_session_factory,
)
from retrieval_service.infrastructure.database.uow import (
    SqlAlchemyRetrievalUnitOfWorkFactory,
)
from retrieval_service.infrastructure.messaging.embedding_gateway import (
    RabbitEmbeddingGateway,
)
from retrieval_service.infrastructure.messaging.rabbitmq import (
    connect_retrieval_broker,
)
from retrieval_service.infrastructure.messaging.schemas import (
    CatalogSourceEvent,
    SourceIndexJobMessage,
)
from retrieval_service.infrastructure.vector_store.qdrant import (
    QdrantManagedSourceVectorStore,
    build_qdrant_client,
)

_LOGGER = logging.getLogger(__name__)
Handler = Callable[[AbstractIncomingMessage], Awaitable[None]]


def build_catalog_handler(
    *,
    register_source: RegisterCatalogSourceUseCase,
    delete_source: DeleteCatalogSourceUseCase,
) -> Handler:
    """Создаёт idempotent handler Catalog source lifecycle events."""

    async def handle(
        message: AbstractIncomingMessage,
    ) -> None:
        """Валидирует event, применяет lifecycle use-case и ack/nack сообщение."""
        event: CatalogSourceEvent | None = None

        try:
            event = CatalogSourceEvent.model_validate_json(message.body)
            payload = event.source

            with scoped_log_context(
                correlation_id=str(event.event_id),
                source_id=str(payload.source_id),
            ):
                common = {
                    "source_id": payload.source_id,
                    "user_id": payload.user_id,
                    "section_id": payload.section_id,
                    "kind": SourceKind(payload.kind),
                    "original_name": payload.original_name,
                    "mime_type": payload.mime_type,
                    "source_sha256": payload.sha256,
                    "occurred_at": event.occurred_at,
                }

                if event.event_type == "catalog.source.uploaded.v1":
                    await register_source.execute(**common)
                else:
                    await delete_source.execute(**common)

                await message.ack()

        except (
            ValidationError,
            RetrievalValidationError,
            RetrievalSourceConflictError,
        ) as exc:
            await message.reject(requeue=False)
            _LOGGER.error(
                "Catalog source event rejected",
                extra={
                    "event": "retrieval_catalog_event_rejected",
                    "event_id": (str(event.event_id) if event is not None else None),
                    "error_type": type(exc).__name__,
                },
            )

        except Exception:
            await message.nack(requeue=True)
            _LOGGER.exception(
                "Catalog source event failed",
                extra={"event": "retrieval_catalog_event_failed"},
            )

    return handle


def build_index_handler(
    index_source: IndexManagedSourceUseCase,
) -> Handler:
    """Создаёт bounded handler expensive normalized source indexing queue."""

    async def handle(
        message: AbstractIncomingMessage,
    ) -> None:
        """Выполняет reindex без бесконечного poison-message requeue."""
        job_message: SourceIndexJobMessage | None = None

        try:
            job_message = SourceIndexJobMessage.model_validate_json(message.body)

            job = IndexSourceJob(
                job_id=job_message.job_id,
                source_id=job_message.source_id,
                source_sha256=job_message.source_sha256,
                correlation_id=job_message.correlation_id,
                chunks=tuple(
                    NormalizedChunk(
                        chunk_id=chunk.chunk_id,
                        text=chunk.text,
                        page_number=chunk.page_number,
                        fragment_index=chunk.fragment_index,
                        heading=chunk.heading,
                        char_start=chunk.char_start,
                        char_end=chunk.char_end,
                    )
                    for chunk in job_message.chunks
                ),
            )

            with scoped_log_context(
                correlation_id=job.correlation_id,
                job_id=str(job.job_id),
                source_id=str(job.source_id),
            ):
                result = await index_source.execute(job)
                await message.ack()

                _LOGGER.info(
                    "Managed source indexing completed",
                    extra={
                        "event": "retrieval_index_completed",
                        "fingerprint": result.fingerprint,
                        "chunk_count": result.chunk_count,
                        "reused": result.reused,
                    },
                )

        except (
            ValidationError,
            RetrievalValidationError,
            RetrievalSourceConflictError,
            RetrievalSourceNotFoundError,
        ) as exc:
            await message.reject(requeue=False)

            _LOGGER.error(
                "Managed source indexing job rejected",
                extra={
                    "event": "retrieval_index_rejected",
                    "job_id": (str(job_message.job_id) if job_message is not None else None),
                    "error_type": type(exc).__name__,
                },
            )

        except RetrievalDependencyError as exc:
            await _bounded_index_retry(
                message=message,
                job_message=job_message,
                error=exc,
                event="retrieval_index_dependency_failed",
            )

        except Exception as exc:
            await _bounded_index_retry(
                message=message,
                job_message=job_message,
                error=exc,
                event="retrieval_index_unexpected_error",
            )

    return handle


async def _bounded_index_retry(
    *,
    message: AbstractIncomingMessage,
    job_message: SourceIndexJobMessage | None,
    error: Exception,
    event: str,
) -> None:
    """Разрешает одну broker redelivery и затем завершает poison delivery."""
    job_id = str(job_message.job_id) if job_message is not None else None

    if message.redelivered:
        await message.reject(requeue=False)

        _LOGGER.error(
            "Managed source indexing retry exhausted",
            extra={
                "event": "retrieval_index_retry_exhausted",
                "job_id": job_id,
                "error_type": type(error).__name__,
                "redelivered": True,
            },
        )
        return

    await message.nack(requeue=True)

    _LOGGER.error(
        "Managed source indexing scheduled for one redelivery",
        extra={
            "event": event,
            "job_id": job_id,
            "error_type": type(error).__name__,
            "redelivered": False,
        },
    )


async def run_worker(
    settings: RetrievalWorkerSettings,
) -> None:
    """Запускает два bounded consumers без GPU runtime внутри Retrieval."""
    engine = create_retrieval_engine(settings)
    session_factory = create_retrieval_session_factory(engine)
    uow_factory = SqlAlchemyRetrievalUnitOfWorkFactory(session_factory)

    qdrant = settings.retrieval_qdrant

    client = build_qdrant_client(
        host=qdrant.host,
        http_port=qdrant.http_port,
        grpc_port=qdrant.grpc_port,
        prefer_grpc=qdrant.prefer_grpc,
        timeout_seconds=qdrant.timeout_seconds,
    )

    vector_store = QdrantManagedSourceVectorStore(
        client=client,
        alias_name=qdrant.alias_name,
        expected_vector_size=qdrant.vector_size,
    )

    embedding_gateway = RabbitEmbeddingGateway(settings)

    register_source = RegisterCatalogSourceUseCase(uow_factory)

    delete_source = DeleteCatalogSourceUseCase(
        uow_factory=uow_factory,
        vector_store=vector_store,
    )

    index_source = IndexManagedSourceUseCase(
        uow_factory=uow_factory,
        embedding_gateway=embedding_gateway,
        vector_store=vector_store,
        clock=SystemClock(),
        expected_model=settings.retrieval_embedding.model_name,
        expected_dimension=(settings.retrieval_embedding.vector_dimension),
        max_chunks=(settings.retrieval_indexing.max_chunks_per_source),
        max_chunk_chars=(settings.retrieval_indexing.max_chunk_chars),
    )

    connection = await connect_retrieval_broker(settings)

    try:
        catalog_channel = await connection.channel()

        await catalog_channel.set_qos(
            prefetch_count=(settings.retrieval_queues.catalog_prefetch_count)
        )

        exchange = await catalog_channel.declare_exchange(
            settings.retrieval_queues.catalog_exchange_name,
            ExchangeType.TOPIC,
            durable=True,
            auto_delete=False,
        )

        catalog_queue = await catalog_channel.declare_queue(
            settings.retrieval_queues.catalog_queue_name,
            durable=True,
            auto_delete=False,
        )

        await catalog_queue.bind(
            exchange,
            routing_key="catalog.source.uploaded.v1",
        )
        await catalog_queue.bind(
            exchange,
            routing_key="catalog.source.delete_requested.v1",
        )

        await catalog_queue.consume(
            build_catalog_handler(
                register_source=register_source,
                delete_source=delete_source,
            ),
            no_ack=False,
        )

        index_channel = await connection.channel()

        await index_channel.set_qos(prefetch_count=(settings.retrieval_queues.index_prefetch_count))

        index_queue = await index_channel.declare_queue(
            settings.retrieval_queues.index_queue_name,
            durable=True,
            auto_delete=False,
        )

        await index_queue.consume(
            build_index_handler(index_source),
            no_ack=False,
        )

        _LOGGER.info(
            "Retrieval worker started",
            extra={
                "event": "retrieval_worker_started",
                "catalog_queue": (settings.retrieval_queues.catalog_queue_name),
                "catalog_prefetch": (settings.retrieval_queues.catalog_prefetch_count),
                "index_queue": (settings.retrieval_queues.index_queue_name),
                "index_prefetch": (settings.retrieval_queues.index_prefetch_count),
                "embedding_queue": (settings.retrieval_queues.embedding_queue_name),
            },
        )

        await asyncio.Future()

    finally:
        await connection.close()
        await client.close()
        await engine.dispose()


def main() -> None:
    """Настраивает structured logging и запускает Retrieval worker."""
    settings = load_retrieval_worker_settings()

    configure_logging(
        service_name=settings.service_name,
        level=settings.log_level.value,
        log_root_dir=settings.log_root_dir,
        log_to_file=settings.log_to_file,
        file_max_bytes=settings.log_file_max_bytes,
        file_backup_count=settings.log_file_backup_count,
        retention_days=settings.log_retention_days,
    )

    asyncio.run(run_worker(settings))


if __name__ == "__main__":
    main()
