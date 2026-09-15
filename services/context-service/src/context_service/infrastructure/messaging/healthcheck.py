# services/context-service/src/context_service/infrastructure/messaging/healthcheck.py

"""Dependency healthcheck background Context processes."""

import asyncio

from context_service.application.use_cases.runtime_status import (
    CheckContextReadinessUseCase,
)
from context_service.core.settings import (
    load_context_settings,
)
from context_service.infrastructure.database.engine import (
    create_context_engine,
    create_context_session_factory,
)
from context_service.infrastructure.database.health import (
    SqlAlchemyDatabaseHealthProbe,
)
from context_service.infrastructure.messaging.health import (
    RabbitBrokerHealthProbe,
)
from context_service.infrastructure.vector_store.health import (
    QdrantHealthProbe,
)
from context_service.infrastructure.vector_store.qdrant import (
    build_qdrant_client,
)


async def check_runtime() -> bool:
    """Проверяет PostgreSQL, Qdrant и mandatory Rabbit queues."""
    settings = load_context_settings()

    engine = create_context_engine(settings)

    session_factory = create_context_session_factory(engine)

    qdrant = settings.context_qdrant

    qdrant_client = build_qdrant_client(
        host=qdrant.host,
        http_port=qdrant.http_port,
        grpc_port=qdrant.grpc_port,
        prefer_grpc=qdrant.prefer_grpc,
        timeout_seconds=qdrant.timeout_seconds,
    )

    try:
        use_case = CheckContextReadinessUseCase(
            database=SqlAlchemyDatabaseHealthProbe(session_factory),
            vector_store=QdrantHealthProbe(qdrant_client),
            broker=RabbitBrokerHealthProbe(settings),
        )

        return await use_case.execute()

    finally:
        await qdrant_client.close()
        await engine.dispose()


def main() -> None:
    """Завершает process code 0 только при полной runtime readiness."""
    try:
        ready = asyncio.run(check_runtime())

    except Exception:
        ready = False

    raise SystemExit(0 if ready else 1)


if __name__ == "__main__":
    main()
