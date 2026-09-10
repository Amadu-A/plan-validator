# services/embedding-service/src/embedding_service/infrastructure/messaging/healthcheck.py

"""Container healthcheck RabbitMQ consumer prerequisites."""

import asyncio

from embedding_service.core.settings import load_embedding_worker_settings
from embedding_service.infrastructure.messaging.rabbitmq import connect_embedding_broker
from embedding_service.infrastructure.model_cache import HuggingFaceModelCacheProbe


async def check() -> None:
    """Проверяет local cache и возможность passive query dedicated queue."""
    settings = load_embedding_worker_settings()
    cache_probe = HuggingFaceModelCacheProbe(
        hf_home=settings.embedding_model.hf_home,
        model_name=settings.embedding_model.name,
    )

    if cache_probe.resolve_snapshot() is None:
        raise RuntimeError("Embedding model cache is not ready")

    connection = await connect_embedding_broker(settings)

    async with connection:
        channel = await connection.channel()
        await channel.declare_queue(
            settings.embedding_queue.name,
            passive=True,
        )


def main() -> None:
    """Запускает async healthcheck как one-shot process."""
    asyncio.run(check())


if __name__ == "__main__":
    main()
