# services/api-gateway/src/api_gateway/application/internal_service.py

"""Application port для HTTP-взаимодействия Gateway с internal services."""

from collections.abc import Mapping
from typing import Any, Protocol

JsonObject = dict[str, Any]


class InternalServiceClient(Protocol):
    """Определяет transport-neutral contract вызова внутреннего сервиса."""

    async def get_json(self, path: str) -> JsonObject:
        """Получает JSON object по internal HTTP endpoint."""
        ...

    async def post_json(
        self,
        path: str,
        payload: Mapping[str, object],
    ) -> JsonObject:
        """Отправляет JSON object во внутренний сервис и возвращает JSON object."""
        ...

    async def aclose(self) -> None:
        """Освобождает принадлежащие client сетевые resources."""
        ...
