# services/api-gateway/src/api_gateway/infrastructure/context_client.py

"""HTTP adapter API Gateway -> Context Service."""

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

from api_gateway.application.context_service import (
    ContextSourceKind,
    ContextSourceState,
    GatewayContextSource,
    GatewayProjectContext,
    ProjectContextState,
)
from api_gateway.infrastructure.http_context import (
    build_context_headers,
)


class HttpContextServiceClient:
    """Реализует Gateway Context port через bounded internal HTTP."""

    def __init__(
        self,
        *,
        base_url: str,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Создаёт bounded HTTPX client без автоматических unsafe retries."""
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

    async def create_context(
        self,
        *,
        user_id: UUID,
    ) -> GatewayProjectContext:
        """Создаёт temporary Project Context для authenticated user."""
        response = await self._request(
            method="POST",
            path="/internal/v1/context/contexts",
            json_body={
                "user_id": str(user_id),
            },
        )

        self._raise_for_error(response)

        if response.status_code != 201:
            raise ExternalDependencyError("Unexpected Context Service create status")

        context = self._parse_context(self._json_object(response))

        self._validate_context_identity(
            context=context,
            expected_user_id=user_id,
            expected_context_id=None,
        )

        return context

    async def get_context(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
    ) -> GatewayProjectContext:
        """Получает owner-scoped Project Context."""
        response = await self._request(
            method="GET",
            path=(f"/internal/v1/context/contexts/{context_id}"),
            params={
                "user_id": str(user_id),
            },
        )

        self._raise_for_error(response)

        if response.status_code != 200:
            raise ExternalDependencyError("Unexpected Context Service get status")

        context = self._parse_context(self._json_object(response))

        self._validate_context_identity(
            context=context,
            expected_user_id=user_id,
            expected_context_id=context_id,
        )

        return context

    async def request_cleanup(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
    ) -> GatewayProjectContext:
        """Запускает logical cleanup без ожидания physical Qdrant deletion."""
        response = await self._request(
            method="DELETE",
            path=(f"/internal/v1/context/contexts/{context_id}"),
            params={
                "user_id": str(user_id),
            },
        )

        self._raise_for_error(response)

        if response.status_code != 202:
            raise ExternalDependencyError("Unexpected Context Service cleanup status")

        context = self._parse_context(self._json_object(response))

        self._validate_context_identity(
            context=context,
            expected_user_id=user_id,
            expected_context_id=context_id,
        )

        return context

    async def register_source(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
        kind: ContextSourceKind,
        original_name: str,
        source_sha256: str,
    ) -> GatewayContextSource:
        """Передаёт Context metadata, но не raw file и не normalized chunks."""
        response = await self._request(
            method="POST",
            path=(f"/internal/v1/context/contexts/{context_id}/sources"),
            json_body={
                "user_id": str(user_id),
                "kind": kind.value,
                "original_name": original_name,
                "source_sha256": source_sha256,
            },
        )

        self._raise_for_error(response)

        if response.status_code != 201:
            raise ExternalDependencyError("Unexpected Context Service source registration status")

        source = self._parse_source(self._json_object(response))

        if source.user_id != user_id or source.context_id != context_id or source.kind is not kind:
            raise ExternalDependencyError("Context Service source identity mismatch")

        return source

    async def aclose(self) -> None:
        """Закрывает HTTPX connection pool."""
        await self._client.aclose()

    @log_execution_time("api_gateway.context_service.request")
    async def _request(
        self,
        *,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> httpx.Response:
        """Выполняет bounded request с correlation headers без body logging."""
        try:
            response = await self._client.request(
                method=method,
                url=path,
                params=params,
                json=json_body,
                headers=build_context_headers(),
            )

        except (
            httpx.TimeoutException,
            httpx.TransportError,
        ) as exc:
            raise TemporaryDependencyError("Context Service is temporarily unavailable") from exc

        if response.status_code >= 500:
            raise TemporaryDependencyError("Context Service returned server error")

        return response

    def _raise_for_error(
        self,
        response: httpx.Response,
    ) -> None:
        """Преобразует internal Context 4xx contract в Gateway errors."""
        if response.status_code < 400:
            return

        payload = self._json_object(response)

        raw_error = payload.get("error")

        if not isinstance(
            raw_error,
            dict,
        ):
            raise ExternalDependencyError("Context Service error contract is invalid")

        message = str(
            raw_error.get(
                "message",
                "Context request failed",
            )
        )

        if response.status_code == 404:
            raise ResourceNotFoundError(message)

        if response.status_code == 409:
            raise ResourceConflictError(message)

        if response.status_code in {
            400,
            422,
        }:
            raise ApplicationError(message)

        raise ExternalDependencyError("Unexpected Context Service error")

    @staticmethod
    def _json_object(
        response: httpx.Response,
    ) -> dict[str, Any]:
        """Парсит JSON object internal Context response."""
        try:
            payload = response.json()

        except ValueError as exc:
            raise ExternalDependencyError("Context Service returned invalid JSON") from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise ExternalDependencyError("Context Service returned invalid object")

        return payload

    @classmethod
    def _parse_context(
        cls,
        payload: dict[str, Any],
    ) -> GatewayProjectContext:
        """Преобразует internal Context JSON в Gateway DTO."""
        try:
            return GatewayProjectContext(
                id=UUID(str(payload["id"])),
                user_id=UUID(str(payload["user_id"])),
                state=ProjectContextState(str(payload["state"])),
                created_at=cls._parse_datetime(payload["created_at"]),
                updated_at=cls._parse_datetime(payload["updated_at"]),
                expires_at=cls._parse_datetime(payload["expires_at"]),
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise ExternalDependencyError("Context Service context response is invalid") from exc

    @classmethod
    def _parse_source(
        cls,
        payload: dict[str, Any],
    ) -> GatewayContextSource:
        """Преобразует internal source JSON в Gateway DTO."""
        try:
            active_fingerprint_raw = payload.get("active_fingerprint")

            return GatewayContextSource(
                id=UUID(str(payload["id"])),
                context_id=UUID(str(payload["context_id"])),
                user_id=UUID(str(payload["user_id"])),
                kind=ContextSourceKind(str(payload["kind"])),
                original_name=str(payload["original_name"]),
                source_sha256=str(payload["source_sha256"]),
                state=ContextSourceState(str(payload["state"])),
                active_fingerprint=(
                    None if active_fingerprint_raw is None else str(active_fingerprint_raw)
                ),
                chunk_count=int(payload["chunk_count"]),
                created_at=cls._parse_datetime(payload["created_at"]),
                updated_at=cls._parse_datetime(payload["updated_at"]),
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise ExternalDependencyError("Context Service source response is invalid") from exc

    @staticmethod
    def _parse_datetime(
        value: object,
    ) -> datetime:
        """Парсит ISO-8601 timestamp internal service response."""
        return datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00",
            )
        )

    @staticmethod
    def _validate_context_identity(
        *,
        context: GatewayProjectContext,
        expected_user_id: UUID,
        expected_context_id: UUID | None,
    ) -> None:
        """Защищает Gateway от confused-deputy downstream response."""
        if context.user_id != expected_user_id:
            raise ExternalDependencyError("Context Service owner identity mismatch")

        if expected_context_id is not None and context.id != expected_context_id:
            raise ExternalDependencyError("Context Service context identity mismatch")
