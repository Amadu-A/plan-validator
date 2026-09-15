# services/context-service/src/context_service/infrastructure/vector_store/health.py

"""Qdrant health probe Context Service."""

from qdrant_client import AsyncQdrantClient


class QdrantHealthProbe:
    """Проверяет Qdrant без требования уже созданной Context collection."""

    def __init__(
        self,
        client: AsyncQdrantClient,
    ) -> None:
        """Сохраняет shared async client."""
        self._client = client

    async def ready(self) -> bool:
        """Возвращает False при недоступном Qdrant endpoint."""
        try:
            await self._client.get_collections()
        except Exception:
            return False

        return True
