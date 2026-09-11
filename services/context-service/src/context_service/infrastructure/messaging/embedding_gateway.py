# services/context-service/src/context_service/infrastructure/messaging/embedding_gateway.py

"""RabbitMQ RPC adapter существующей batch embedding GPU queue."""

import asyncio
import json
from datetime import timedelta
from uuid import uuid4

from aio_pika import DeliveryMode, Message
from aio_pika.abc import AbstractIncomingMessage
from plan_validator_common.vector_codec import (
    FLOAT32_BASE64_ENCODING,
    decode_float32_vectors,
)

from context_service.application.ports.embedding_gateway import (
    ContextEmbeddingGateway,
    EmbeddedContextTexts,
)
from context_service.core.settings import ContextSettings
from context_service.domain.exceptions import ContextEmbeddingError
from context_service.infrastructure.messaging.rabbitmq import connect_context_broker


class RabbitContextEmbeddingGateway(ContextEmbeddingGateway):
    """Вызывает serialized GPU queue через bounded RPC без прямого GPU доступа."""

    def __init__(self, settings: ContextSettings) -> None:
        """Сохраняет broker/embedding settings."""
        self._settings = settings

    async def embed_texts(
        self,
        *,
        texts: tuple[str, ...],
        instruction: str,
        correlation_id: str,
    ) -> EmbeddedContextTexts:
        """Отправляет batch request и декодирует compact float32 response."""
        if not texts:
            raise ContextEmbeddingError("Embedding request must contain texts")

        connection = None
        body: bytes

        try:
            connection = await connect_context_broker(self._settings)
            channel = await connection.channel()
            callback_queue = await channel.declare_queue(
                exclusive=True,
                auto_delete=True,
            )
            rpc_correlation_id = uuid4().hex
            future: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()

            async def on_response(message: AbstractIncomingMessage) -> None:
                """Принимает только RPC response текущего correlation id."""
                async with message.process(ignore_processed=True):
                    if message.correlation_id != rpc_correlation_id or future.done():
                        return
                    future.set_result(message.body)

            consumer_tag = await callback_queue.consume(on_response)
            request = {
                "schema_version": 1,
                "job_id": str(uuid4()),
                "correlation_id": correlation_id,
                "texts": list(texts),
                "instruction": instruction,
            }
            await channel.default_exchange.publish(
                Message(
                    body=json.dumps(
                        request,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8"),
                    content_type="application/json",
                    content_encoding="utf-8",
                    correlation_id=rpc_correlation_id,
                    reply_to=callback_queue.name,
                    delivery_mode=DeliveryMode.PERSISTENT,
                    expiration=timedelta(
                        seconds=self._settings.context_embedding.rpc_timeout_seconds
                    ),
                ),
                routing_key=self._settings.context_embedding.queue_name,
                mandatory=True,
            )
            body = await asyncio.wait_for(
                future,
                timeout=self._settings.context_embedding.rpc_timeout_seconds,
            )
            await callback_queue.cancel(consumer_tag)
        except TimeoutError as exc:
            raise ContextEmbeddingError("Embedding RPC timeout expired") from exc
        except ContextEmbeddingError:
            raise
        except Exception as exc:
            raise ContextEmbeddingError("Embedding RPC transport failed") from exc
        finally:
            if connection is not None:
                await connection.close()

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContextEmbeddingError("Embedding RPC returned invalid JSON") from exc

        if payload.get("status") != "success":
            error_type = str(payload.get("error_type", "EmbeddingError"))
            message = str(payload.get("message", "Embedding job failed"))
            raise ContextEmbeddingError(f"{error_type}: {message}")

        try:
            model = str(payload["model"])
            dimension = int(payload["dimension"])
            vector_count = int(payload["vector_count"])
            vector_encoding = str(payload["vector_encoding"])
            vectors_b64 = str(payload["vectors_b64"])

            if vector_encoding != FLOAT32_BASE64_ENCODING:
                raise ValueError(f"Unsupported embedding vector encoding: {vector_encoding}")

            vectors = decode_float32_vectors(
                vectors_b64,
                vector_count=vector_count,
                dimension=dimension,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ContextEmbeddingError(
                "Embedding RPC returned invalid compact batch payload"
            ) from exc

        if vector_count != len(texts):
            raise ContextEmbeddingError(
                "Embedding RPC vector count does not match request text count"
            )

        return EmbeddedContextTexts(
            model=model,
            dimension=dimension,
            vectors=vectors,
        )
