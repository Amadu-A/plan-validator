# services/embedding-service/src/embedding_service/infrastructure/messaging/worker.py

"""RabbitMQ consumer dedicated GPU embedding queue."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

from aio_pika import DeliveryMode, Message
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage
from plan_validator_common.observability import configure_logging, scoped_log_context
from plan_validator_common.vector_codec import (
    FLOAT32_BASE64_ENCODING,
    encode_float32_vectors,
)
from pydantic import ValidationError

from embedding_service.application.use_cases.embed_text import (
    EmbedTextsUseCase,
    EmbedTextUseCase,
)
from embedding_service.core.settings import (
    EmbeddingWorkerSettings,
    load_embedding_worker_settings,
)
from embedding_service.domain.embedding import EmbeddingTelemetry
from embedding_service.domain.exceptions import EmbeddingRuntimeError
from embedding_service.infrastructure.gpu_lease import CrossProcessFileGpuLease
from embedding_service.infrastructure.gpu_runtime import QwenEmbeddingRuntime
from embedding_service.infrastructure.messaging.rabbitmq import (
    connect_embedding_broker,
)
from embedding_service.infrastructure.messaging.schemas import (
    EmbeddingBatchJobRequest,
    EmbeddingBatchJobSuccess,
    EmbeddingJobFailure,
    EmbeddingJobRequest,
    EmbeddingJobSuccess,
    EmbeddingTelemetryMessage,
)
from embedding_service.infrastructure.model_cache import HuggingFaceModelCacheProbe

_LOGGER = logging.getLogger(__name__)
Handler = Callable[[AbstractIncomingMessage], Awaitable[None]]


def build_message_handler(
    *,
    single_use_case: EmbedTextUseCase,
    batch_use_case: EmbedTextsUseCase,
    channel: AbstractChannel,
) -> Handler:
    """Создаёт stateless consumer handler single/batch GPU contracts."""

    async def handle(
        message: AbstractIncomingMessage,
    ) -> None:
        """Валидирует request и никогда не создаёт infinite poison requeue."""
        request: EmbeddingJobRequest | EmbeddingBatchJobRequest | None = None

        try:
            raw_payload = json.loads(message.body.decode("utf-8"))

            if isinstance(raw_payload, dict) and "texts" in raw_payload:
                request = EmbeddingBatchJobRequest.model_validate(raw_payload)
            else:
                request = EmbeddingJobRequest.model_validate(raw_payload)

            correlation_id = request.correlation_id
            job_id = str(request.job_id)

            with scoped_log_context(
                correlation_id=correlation_id,
                job_id=job_id,
            ):
                if isinstance(
                    request,
                    EmbeddingBatchJobRequest,
                ):
                    batch_result = await batch_use_case.execute(
                        job_id=request.job_id,
                        texts=request.texts,
                        instruction=request.instruction,
                    )
                    response: EmbeddingJobSuccess | EmbeddingBatchJobSuccess = (
                        EmbeddingBatchJobSuccess(
                            job_id=batch_result.job_id,
                            model=batch_result.model,
                            dimension=batch_result.dimension,
                            vector_encoding=FLOAT32_BASE64_ENCODING,
                            vector_count=len(batch_result.vectors),
                            vectors_b64=encode_float32_vectors(
                                batch_result.vectors,
                                dimension=batch_result.dimension,
                            ),
                            telemetry=_telemetry_message(batch_result.telemetry),
                        )
                    )
                else:
                    result = await single_use_case.execute(
                        job_id=request.job_id,
                        text=request.text,
                        instruction=request.instruction,
                    )
                    response = EmbeddingJobSuccess(
                        job_id=result.job_id,
                        model=result.model,
                        dimension=result.dimension,
                        vector=list(result.vector),
                        telemetry=_telemetry_message(result.telemetry),
                    )

                await _publish_response(
                    channel=channel,
                    message=message,
                    payload=response.model_dump_json(),
                )
                await message.ack()

        except (
            ValidationError,
            EmbeddingRuntimeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            await _finish_with_failure(
                channel=channel,
                message=message,
                request=request,
                error=exc,
            )

        except Exception as exc:
            _LOGGER.exception(
                "Unexpected embedding worker error",
                extra={
                    "event": "embedding_worker_unexpected_error",
                    "job_id": (str(request.job_id) if request is not None else None),
                    "error_type": type(exc).__name__,
                },
            )
            await _finish_with_failure(
                channel=channel,
                message=message,
                request=request,
                error=exc,
            )

    return handle


async def _finish_with_failure(
    *,
    channel: AbstractChannel,
    message: AbstractIncomingMessage,
    request: EmbeddingJobRequest | EmbeddingBatchJobRequest | None,
    error: Exception,
) -> None:
    """Отвечает ошибкой и завершает delivery без бесконечного requeue."""
    failure = EmbeddingJobFailure(
        job_id=(request.job_id if request is not None else None),
        error_type=type(error).__name__,
        message=_safe_error_message(error),
    )

    response_published = False

    if request is not None and message.reply_to:
        try:
            await _publish_response(
                channel=channel,
                message=message,
                payload=failure.model_dump_json(),
            )
            response_published = True
        except Exception:
            _LOGGER.exception(
                "Embedding failure response publish failed",
                extra={
                    "event": "embedding_failure_response_publish_failed",
                    "job_id": str(request.job_id),
                },
            )

    if response_published:
        await message.ack()
    else:
        await message.reject(requeue=False)

    _LOGGER.error(
        "Embedding job failed",
        extra={
            "event": "embedding_job_failed",
            "job_id": (str(request.job_id) if request is not None else None),
            "error_type": type(error).__name__,
            "redelivered": message.redelivered,
        },
    )


def _telemetry_message(
    telemetry: EmbeddingTelemetry,
) -> EmbeddingTelemetryMessage:
    """Преобразует domain telemetry в transport-neutral RPC schema."""
    return EmbeddingTelemetryMessage(
        available_ram_bytes=telemetry.available_ram_bytes,
        free_vram_before_bytes=telemetry.free_vram_before_bytes,
        total_vram_bytes=telemetry.total_vram_bytes,
        model_load_ms=telemetry.model_load_ms,
        encode_ms=telemetry.encode_ms,
        total_ms=telemetry.total_ms,
        peak_allocated_vram_bytes=telemetry.peak_allocated_vram_bytes,
    )


async def _publish_response(
    *,
    channel: AbstractChannel,
    message: AbstractIncomingMessage,
    payload: str,
) -> None:
    """Публикует RPC response только если caller предоставил reply_to."""
    if not message.reply_to:
        return

    await channel.default_exchange.publish(
        Message(
            body=payload.encode("utf-8"),
            content_type="application/json",
            correlation_id=message.correlation_id,
            delivery_mode=DeliveryMode.NOT_PERSISTENT,
        ),
        routing_key=message.reply_to,
    )


def _safe_error_message(
    error: Exception,
) -> str:
    """Не позволяет validation error вернуть исходный document text."""
    if isinstance(
        error,
        (
            ValidationError,
            json.JSONDecodeError,
        ),
    ):
        return "Embedding job payload is invalid"

    return str(error)[:1000]


def build_use_cases(
    settings: EmbeddingWorkerSettings,
) -> tuple[EmbedTextUseCase, EmbedTextsUseCase]:
    """Собирает single/batch use-cases поверх одного serialized GPU runtime."""
    cache_probe = HuggingFaceModelCacheProbe(
        hf_home=settings.embedding_model.hf_home,
        model_name=settings.embedding_model.name,
    )
    lease = CrossProcessFileGpuLease(
        path=settings.embedding_model.gpu_lease_path,
        poll_seconds=settings.embedding_model.gpu_lease_poll_seconds,
    )
    runtime = QwenEmbeddingRuntime(
        settings=settings.embedding_model,
        cache_probe=cache_probe,
        gpu_lease=lease,
    )

    return (
        EmbedTextUseCase(
            runtime=runtime,
            max_text_chars=settings.embedding_model.max_text_chars,
        ),
        EmbedTextsUseCase(
            runtime=runtime,
            max_text_chars=settings.embedding_model.max_text_chars,
            max_job_items=settings.embedding_model.max_job_items,
        ),
    )


async def run_worker(
    settings: EmbeddingWorkerSettings,
) -> None:
    """Подключается к shared broker и consume'ит ровно одну GPU queue."""
    single_use_case, batch_use_case = build_use_cases(settings)
    connection = await connect_embedding_broker(settings)

    async with connection:
        channel = await connection.channel()

        await channel.set_qos(prefetch_count=settings.embedding_queue.prefetch_count)

        queue = await channel.declare_queue(
            settings.embedding_queue.name,
            durable=True,
            auto_delete=False,
        )

        await queue.consume(
            build_message_handler(
                single_use_case=single_use_case,
                batch_use_case=batch_use_case,
                channel=channel,
            ),
            no_ack=False,
        )

        _LOGGER.info(
            "Embedding worker started",
            extra={
                "event": "embedding_worker_started",
                "queue": settings.embedding_queue.name,
                "prefetch_count": (settings.embedding_queue.prefetch_count),
                "model": settings.embedding_model.name,
            },
        )

        await asyncio.Future()


def main() -> None:
    """Настраивает structured logging и запускает worker event loop."""
    settings = load_embedding_worker_settings()

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
