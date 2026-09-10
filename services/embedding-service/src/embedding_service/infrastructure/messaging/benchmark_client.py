# services/embedding-service/src/embedding_service/infrastructure/messaging/benchmark_client.py

"""One-shot RabbitMQ RPC client реального Stage 8 GPU benchmark."""

import asyncio
import json
import math
from uuid import uuid4

from aio_pika import DeliveryMode, Message
from aio_pika.abc import AbstractIncomingMessage

from embedding_service.core.settings import load_embedding_worker_settings
from embedding_service.infrastructure.messaging.rabbitmq import connect_embedding_broker
from embedding_service.infrastructure.messaging.schemas import EmbeddingJobRequest

BENCHMARK_TEXT = (
    "В электроустановках должны быть предусмотрены решения, обеспечивающие "
    "безопасную эксплуатацию, доступность обслуживания и соблюдение требований "
    "проектной и нормативной документации."
)


async def run_benchmark() -> dict[str, object]:
    """Отправляет один job, ждёт reply и проверяет dimension/normalization."""
    settings = load_embedding_worker_settings()
    job_id = uuid4()
    correlation_id = uuid4().hex
    connection = await connect_embedding_broker(settings)

    async with connection:
        channel = await connection.channel()
        callback_queue = await channel.declare_queue(exclusive=True, auto_delete=True)
        future: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()

        async def on_response(message: AbstractIncomingMessage) -> None:
            """Принимает только response текущего correlation identifier."""
            async with message.process(ignore_processed=True):
                if message.correlation_id != correlation_id or future.done():
                    return
                future.set_result(message.body)

        await callback_queue.consume(on_response)
        request = EmbeddingJobRequest(
            job_id=job_id,
            correlation_id=correlation_id,
            text=BENCHMARK_TEXT,
            instruction="Represent this construction requirement for retrieval.",
        )

        await channel.default_exchange.publish(
            Message(
                body=request.model_dump_json().encode("utf-8"),
                content_type="application/json",
                correlation_id=correlation_id,
                reply_to=callback_queue.name,
                delivery_mode=DeliveryMode.PERSISTENT,
            ),
            routing_key=settings.embedding_queue.name,
        )

        body = await asyncio.wait_for(
            future,
            timeout=settings.embedding_queue.rpc_timeout_seconds,
        )

    payload = json.loads(body.decode("utf-8"))

    if payload.get("status") != "success":
        raise RuntimeError(f"Embedding benchmark failed: {payload}")

    vector = payload.get("vector")

    if not isinstance(vector, list):
        raise RuntimeError("Embedding benchmark response has no vector")

    expected_dimension = settings.embedding_model.output_dimension

    if len(vector) != expected_dimension:
        raise RuntimeError(
            f"Embedding dimension mismatch: expected={expected_dimension}, got={len(vector)}"
        )

    norm = math.sqrt(sum(float(value) ** 2 for value in vector))

    if not math.isclose(norm, 1.0, rel_tol=0.01, abs_tol=0.01):
        raise RuntimeError(f"Embedding vector is not normalized: norm={norm}")

    payload["vector"] = "[omitted]"
    payload["vector_norm"] = round(norm, 6)
    payload["verified_dimension"] = len(vector)
    return payload


def main() -> None:
    """Печатает один безопасный JSON benchmark result без полного vector."""
    result = asyncio.run(run_benchmark())
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
