# services/retrieval-service/src/retrieval_service/infrastructure/messaging/embedding_gateway.py

"""RabbitMQ RPC adapter batch text embeddings."""

import asyncio
import json
from uuid import uuid4

from aio_pika import DeliveryMode, Message
from aio_pika.abc import AbstractIncomingMessage
from plan_validator_common.vector_codec import (
    FLOAT32_BASE64_ENCODING,
    decode_float32_vectors,
)

from retrieval_service.application.ports.embedding_gateway import EmbeddedTexts
from retrieval_service.core.settings import RetrievalSettings
from retrieval_service.domain.exceptions import RetrievalEmbeddingError
from retrieval_service.infrastructure.messaging.rabbitmq import connect_retrieval_broker


class RabbitEmbeddingGateway:
    """Вызывает dedicated GPU embedding queue через bounded RPC."""

    def __init__(self, settings: RetrievalSettings) -> None:
        """Сохраняет immutable broker/queue settings."""
        self._settings = settings

    async def embed_texts(
        self,
        *,
        texts: tuple[str, ...],
        instruction: str,
        correlation_id: str,
    ) -> EmbeddedTexts:
        """Отправляет batch job и возвращает vectors в исходном порядке."""
        if not texts:
            raise RetrievalEmbeddingError("Embedding request must contain texts")

        connection = await connect_retrieval_broker(self._settings)

        try:
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
                ),
                routing_key=self._settings.retrieval_queues.embedding_queue_name,
                mandatory=True,
            )

            body = await asyncio.wait_for(
                future,
                timeout=self._settings.retrieval_queues.rpc_timeout_seconds,
            )
            await callback_queue.cancel(consumer_tag)
        except TimeoutError as exc:
            raise RetrievalEmbeddingError("Embedding RPC timeout expired") from exc
        except RetrievalEmbeddingError:
            raise
        except Exception as exc:
            raise RetrievalEmbeddingError("Embedding RPC transport failed") from exc
        finally:
            await connection.close()

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RetrievalEmbeddingError("Embedding RPC returned invalid JSON") from exc

        if payload.get("status") != "success":
            error_type = str(payload.get("error_type", "EmbeddingError"))
            message = str(payload.get("message", "Embedding job failed"))
            raise RetrievalEmbeddingError(f"{error_type}: {message}")

        try:
            model = str(payload["model"])
            dimension = int(payload["dimension"])
            vector_count = int(payload["vector_count"])
            vector_encoding = str(payload["vector_encoding"])
            vectors_b64 = str(payload["vectors_b64"])

            if vector_encoding != FLOAT32_BASE64_ENCODING:
                raise ValueError(f"Unsupported embedding vector encoding: {vector_encoding}")

            normalized_vectors = decode_float32_vectors(
                vectors_b64,
                vector_count=vector_count,
                dimension=dimension,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RetrievalEmbeddingError(
                "Embedding RPC returned invalid compact batch payload"
            ) from exc

        if vector_count != len(texts):
            raise RetrievalEmbeddingError(
                "Embedding RPC vector count does not match request text count"
            )

        return EmbeddedTexts(
            model=model,
            dimension=dimension,
            vectors=normalized_vectors,
        )
