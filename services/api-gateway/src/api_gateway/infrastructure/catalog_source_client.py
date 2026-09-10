# services/api-gateway/src/api_gateway/infrastructure/catalog_source_client.py

"""HTTP adapter Gateway -> Catalog managed source API."""

from datetime import datetime
from typing import Any
from urllib.parse import quote, unquote
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

from api_gateway.application.catalog_sources import (
    CatalogManagedSource,
    CatalogSourceContent,
    CatalogSourceKind,
    CatalogSourceLifecycle,
)
from api_gateway.infrastructure.http_context import build_context_headers


class HttpCatalogSourceServiceClient:
    """Реализует typed managed source port через internal Catalog HTTP."""

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

    async def list_sources(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
        kind: CatalogSourceKind,
    ) -> list[CatalogManagedSource]:
        """Получает managed sources одной section."""
        response = await self._request(
            method="GET",
            path=self._collection_path(
                user_id=user_id,
                kind=kind,
            ),
            params={"section_id": str(section_id)},
        )

        self._raise_for_error(response)
        payload = self._json_object(response)
        raw_sources = payload.get("sources")

        if not isinstance(raw_sources, list):
            raise ExternalDependencyError("Catalog Service source list response is invalid")

        return [self._parse_source(item) for item in raw_sources if isinstance(item, dict)]

    async def upload_source(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
        kind: CatalogSourceKind,
        file_name: str,
        content: bytes,
    ) -> CatalogManagedSource:
        """Передаёт raw source bytes в internal Catalog API."""
        response = await self._request(
            method="POST",
            path=self._collection_path(
                user_id=user_id,
                kind=kind,
            ),
            params={"section_id": str(section_id)},
            content=content,
            extra_headers={
                "Content-Type": "application/octet-stream",
                "X-Source-Filename": quote(
                    file_name,
                    safe="",
                ),
            },
        )

        self._raise_for_error(response)

        if response.status_code != 201:
            raise ExternalDependencyError("Unexpected Catalog source upload status")

        return self._parse_source(self._json_object(response))

    async def get_source(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: CatalogSourceKind,
    ) -> CatalogManagedSource:
        """Получает metadata managed source."""
        response = await self._request(
            method="GET",
            path=self._resource_path(
                user_id=user_id,
                source_id=source_id,
                kind=kind,
            ),
        )

        self._raise_for_error(response)
        return self._parse_source(self._json_object(response))

    async def get_source_content(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: CatalogSourceKind,
    ) -> CatalogSourceContent:
        """Получает bytes и filename metadata internal content endpoint."""
        response = await self._request(
            method="GET",
            path=(
                f"{self._resource_path(user_id=user_id, source_id=source_id, kind=kind)}/content"
            ),
        )

        self._raise_for_error(response)

        encoded_name = response.headers.get("x-source-filename")
        content_type = response.headers.get("content-type")

        if not encoded_name or not content_type:
            raise ExternalDependencyError("Catalog Service content headers are invalid")

        try:
            file_name = unquote(
                encoded_name,
                encoding="utf-8",
                errors="strict",
            )
        except UnicodeDecodeError as exc:
            raise ExternalDependencyError("Catalog Service content filename is invalid") from exc

        return CatalogSourceContent(
            source_id=source_id,
            file_name=file_name,
            mime_type=content_type.split(";", maxsplit=1)[0].strip(),
            content=response.content,
        )

    async def delete_source(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: CatalogSourceKind,
    ) -> None:
        """Запускает managed source delete lifecycle."""
        response = await self._request(
            method="DELETE",
            path=self._resource_path(
                user_id=user_id,
                source_id=source_id,
                kind=kind,
            ),
        )

        self._raise_for_error(response)

        if response.status_code != 204:
            raise ExternalDependencyError("Unexpected Catalog source delete status")

    async def aclose(self) -> None:
        """Закрывает HTTPX connection pool."""
        await self._client.aclose()

    @log_execution_time("api_gateway.catalog_source_service.request")
    async def _request(
        self,
        *,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        content: bytes | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Выполняет internal request без логирования body/filename."""
        headers = build_context_headers()

        if extra_headers:
            headers.update(extra_headers)

        try:
            response = await self._client.request(
                method=method,
                url=path,
                params=params,
                content=content,
                headers=headers,
            )
        except (
            httpx.TimeoutException,
            httpx.TransportError,
        ) as exc:
            raise TemporaryDependencyError("Catalog Service is temporarily unavailable") from exc

        if response.status_code >= 500:
            raise TemporaryDependencyError("Catalog Service returned server error")

        return response

    def _raise_for_error(self, response: httpx.Response) -> None:
        """Преобразует Catalog source 4xx contract в Gateway errors."""
        if response.status_code < 400:
            return

        payload = self._json_object(response)
        error = payload.get("error")

        if not isinstance(error, dict):
            raise ExternalDependencyError("Catalog Service error contract is invalid")

        message = str(
            error.get(
                "message",
                "Catalog source request failed",
            )
        )

        if response.status_code == 404:
            raise ResourceNotFoundError(message)

        if response.status_code == 409:
            raise ResourceConflictError(message)

        if response.status_code == 400:
            raise ApplicationError(message)

        raise ExternalDependencyError("Unexpected Catalog Service error")

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        """Парсит JSON object Catalog response."""
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalDependencyError("Catalog Service returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise ExternalDependencyError("Catalog Service returned invalid object")

        return payload

    @staticmethod
    def _parse_source(payload: dict[str, Any]) -> CatalogManagedSource:
        """Преобразует internal source JSON в Gateway DTO."""
        try:
            deleted_raw = payload.get("deleted_at")

            return CatalogManagedSource(
                id=UUID(str(payload["id"])),
                section_id=UUID(str(payload["section_id"])),
                kind=CatalogSourceKind(str(payload["kind"])),
                original_name=str(payload["original_name"]),
                mime_type=str(payload["mime_type"]),
                size_bytes=int(payload["size_bytes"]),
                sha256=str(payload["sha256"]),
                lifecycle=CatalogSourceLifecycle(str(payload["lifecycle"])),
                created_at=datetime.fromisoformat(
                    str(payload["created_at"]).replace(
                        "Z",
                        "+00:00",
                    )
                ),
                updated_at=datetime.fromisoformat(
                    str(payload["updated_at"]).replace(
                        "Z",
                        "+00:00",
                    )
                ),
                deleted_at=(
                    datetime.fromisoformat(
                        str(deleted_raw).replace(
                            "Z",
                            "+00:00",
                        )
                    )
                    if deleted_raw is not None
                    else None
                ),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise ExternalDependencyError("Catalog Service source response is invalid") from exc

    @staticmethod
    def _collection_path(
        *,
        user_id: UUID,
        kind: CatalogSourceKind,
    ) -> str:
        """Возвращает kind-specific internal collection path."""
        resource = (
            "normative-documents" if kind is CatalogSourceKind.NORMATIVE else "user-documents"
        )

        return f"/internal/v1/catalog/users/{user_id}/{resource}"

    @classmethod
    def _resource_path(
        cls,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: CatalogSourceKind,
    ) -> str:
        """Возвращает kind-specific internal resource path."""
        return f"{cls._collection_path(user_id=user_id, kind=kind)}/{source_id}"
