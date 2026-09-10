# services/api-gateway/src/api_gateway/infrastructure/catalog_client.py

"""HTTP adapter Gateway -> Catalog Service."""

from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from plan_validator_common.exceptions import (
    ApplicationError,
    ExternalDependencyError,
    ResourceConflictError,
    ResourceNotFoundError,
    TemporaryDependencyError,
)
from plan_validator_common.observability import log_execution_time

from api_gateway.application.catalog_service import (
    CatalogSection,
    CatalogSystemPrompt,
)
from api_gateway.infrastructure.http_context import build_context_headers


class HttpCatalogServiceClient:
    """Реализует typed CatalogServiceClient через internal HTTP."""

    def __init__(
        self,
        *,
        base_url: str,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Создаёт bounded HTTPX client."""
        timeout = httpx.Timeout(
            timeout=read_timeout_seconds,
            connect=connect_timeout_seconds,
        )

        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            follow_redirects=False,
            transport=transport,
        )

    async def list_sections(
        self,
        *,
        user_id: UUID,
    ) -> list[CatalogSection]:
        """Получает user-scoped sections."""
        response = await self._request(
            method="GET",
            path=f"/internal/v1/catalog/users/{user_id}/sections",
        )

        self._raise_for_error(response)

        payload = self._json_object(response)
        raw_sections = payload.get("sections")

        if not isinstance(raw_sections, list):
            raise ExternalDependencyError(
                "Catalog Service section list response is invalid"
            )

        return [
            self._parse_section(item)
            for item in raw_sections
            if isinstance(item, dict)
        ]

    async def create_section(
        self,
        *,
        user_id: UUID,
        title: str,
        parent_id: UUID | None,
        sort_order: int,
    ) -> CatalogSection:
        """Создаёт section через internal Catalog API."""
        response = await self._request(
            method="POST",
            path=f"/internal/v1/catalog/users/{user_id}/sections",
            payload={
                "title": title,
                "parent_id": str(parent_id) if parent_id is not None else None,
                "sort_order": sort_order,
            },
        )

        self._raise_for_error(response)

        if response.status_code != 201:
            raise ExternalDependencyError(
                "Unexpected Catalog create status"
            )

        return self._parse_section(self._json_object(response))

    async def update_section(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
        title: str | None,
        parent_id: UUID | None,
        parent_id_supplied: bool,
        sort_order: int | None,
    ) -> CatalogSection:
        """Изменяет section и сохраняет omitted/null semantics."""
        payload: dict[str, object] = {}

        if title is not None:
            payload["title"] = title

        if parent_id_supplied:
            payload["parent_id"] = (
                str(parent_id)
                if parent_id is not None
                else None
            )

        if sort_order is not None:
            payload["sort_order"] = sort_order

        response = await self._request(
            method="PATCH",
            path=(
                f"/internal/v1/catalog/users/{user_id}"
                f"/sections/{section_id}"
            ),
            payload=payload,
        )

        self._raise_for_error(response)

        return self._parse_section(self._json_object(response))

    async def delete_section(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> None:
        """Удаляет section через internal Catalog API."""
        response = await self._request(
            method="DELETE",
            path=(
                f"/internal/v1/catalog/users/{user_id}"
                f"/sections/{section_id}"
            ),
        )

        self._raise_for_error(response)

        if response.status_code != 204:
            raise ExternalDependencyError(
                "Unexpected Catalog delete status"
            )

    async def get_system_prompt(
        self,
        *,
        user_id: UUID,
    ) -> CatalogSystemPrompt:
        """Получает сохранённый prompt."""
        response = await self._request(
            method="GET",
            path=f"/internal/v1/catalog/users/{user_id}/system-prompt",
        )

        self._raise_for_error(response)

        return self._parse_system_prompt(
            self._json_object(response)
        )

    async def save_system_prompt(
        self,
        *,
        user_id: UUID,
        prompt: str,
    ) -> CatalogSystemPrompt:
        """Сохраняет prompt через internal Catalog API."""
        response = await self._request(
            method="PUT",
            path=f"/internal/v1/catalog/users/{user_id}/system-prompt",
            payload={"prompt": prompt},
        )

        self._raise_for_error(response)

        return self._parse_system_prompt(
            self._json_object(response)
        )

    async def aclose(self) -> None:
        """Закрывает HTTPX connection pool."""
        await self._client.aclose()

    @log_execution_time("api_gateway.catalog_service.request")
    async def _request(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> httpx.Response:
        """Выполняет internal request без логирования body."""
        try:
            response = await self._client.request(
                method=method,
                url=path,
                json=payload,
                headers=build_context_headers(),
            )
        except (
            httpx.TimeoutException,
            httpx.TransportError,
        ) as exc:
            raise TemporaryDependencyError(
                "Catalog Service is temporarily unavailable"
            ) from exc

        if response.status_code >= 500:
            raise TemporaryDependencyError(
                "Catalog Service returned server error"
            )

        return response

    def _raise_for_error(self, response: httpx.Response) -> None:
        """Преобразует Catalog 4xx contract в Gateway project errors."""
        if response.status_code < 400:
            return

        payload = self._json_object(response)
        error = payload.get("error")

        if not isinstance(error, dict):
            raise ExternalDependencyError(
                "Catalog Service error contract is invalid"
            )

        message = str(error.get("message", "Catalog request failed"))

        if response.status_code == 404:
            raise ResourceNotFoundError(message)

        if response.status_code == 409:
            raise ResourceConflictError(message)

        if response.status_code == 400:
            raise ApplicationError(message)

        raise ExternalDependencyError(
            "Unexpected Catalog Service error"
        )

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        """Парсит JSON object Catalog response."""
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalDependencyError(
                "Catalog Service returned invalid JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise ExternalDependencyError(
                "Catalog Service returned invalid object"
            )

        return payload

    @staticmethod
    def _parse_section(payload: dict[str, Any]) -> CatalogSection:
        """Преобразует internal section JSON в Gateway DTO."""
        try:
            parent_raw = payload.get("parent_id")

            return CatalogSection(
                id=UUID(str(payload["id"])),
                parent_id=(
                    UUID(str(parent_raw))
                    if parent_raw is not None
                    else None
                ),
                title=str(payload["title"]),
                sort_order=int(payload["sort_order"]),
                created_at=datetime.fromisoformat(
                    str(payload["created_at"]).replace("Z", "+00:00")
                ),
                updated_at=datetime.fromisoformat(
                    str(payload["updated_at"]).replace("Z", "+00:00")
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ExternalDependencyError(
                "Catalog Service section response is invalid"
            ) from exc

    @staticmethod
    def _parse_system_prompt(
        payload: dict[str, Any],
    ) -> CatalogSystemPrompt:
        """Преобразует prompt JSON в Gateway DTO."""
        try:
            updated_raw = payload.get("updated_at")

            return CatalogSystemPrompt(
                prompt=str(payload["prompt"]),
                updated_at=(
                    datetime.fromisoformat(
                        str(updated_raw).replace("Z", "+00:00")
                    )
                    if updated_raw is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ExternalDependencyError(
                "Catalog Service prompt response is invalid"
            ) from exc
