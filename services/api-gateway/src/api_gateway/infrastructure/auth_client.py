# services/api-gateway/src/api_gateway/infrastructure/auth_client.py

"""HTTP adapter Gateway -> trusted Authentication Service."""

from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from plan_validator_common.exceptions import (
    AuthenticationError,
    ExternalDependencyError,
    ResourceConflictError,
    ResourceNotFoundError,
    TemporaryDependencyError,
)
from plan_validator_common.observability import (
    log_execution_time,
)

from api_gateway.application.auth_service import (
    AuthSession,
    AuthUser,
)
from api_gateway.infrastructure.http_context import (
    build_context_headers,
)


class HttpAuthServiceClient:
    """Реализует typed AuthServiceClient через internal HTTP API."""

    def __init__(
        self,
        *,
        base_url: str,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Создаёт bounded HTTPX pool только для Auth Service."""
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

    async def register_user(
        self,
        *,
        email: str,
        password: str,
    ) -> AuthSession:
        """Вызывает internal registration endpoint."""
        response = await self._request(
            method="POST",
            path="/internal/v1/auth/register",
            payload={
                "email": email,
                "password": password,
            },
        )

        self._raise_for_business_error(response)

        if response.status_code != 201:
            raise ExternalDependencyError("Unexpected Auth registration status")

        return self._parse_auth_session(self._json_object(response))

    async def login_user(
        self,
        *,
        email: str,
        password: str,
    ) -> AuthSession:
        """Вызывает internal password login endpoint."""
        response = await self._request(
            method="POST",
            path="/internal/v1/auth/login",
            payload={
                "email": email,
                "password": password,
            },
        )

        self._raise_for_business_error(response)

        if response.status_code != 200:
            raise ExternalDependencyError("Unexpected Auth login status")

        return self._parse_auth_session(self._json_object(response))

    async def logout_session(
        self,
        *,
        session_token: str,
    ) -> None:
        """Отзывает session в Auth Service."""
        response = await self._request(
            method="POST",
            path="/internal/v1/auth/logout",
            payload={
                "session_token": (session_token),
            },
        )

        self._raise_for_business_error(response)

        if response.status_code != 204:
            raise ExternalDependencyError("Unexpected Auth logout status")

    async def get_current_user(
        self,
        *,
        session_token: str,
    ) -> AuthUser:
        """Разрешает opaque token через internal session endpoint."""
        response = await self._request(
            method="POST",
            path="/internal/v1/auth/session",
            payload={
                "session_token": (session_token),
            },
        )

        self._raise_for_business_error(response)

        if response.status_code != 200:
            raise ExternalDependencyError("Unexpected Auth session status")

        return self._parse_user(self._json_object(response))

    async def aclose(self) -> None:
        """Закрывает Auth HTTP connection pool."""
        await self._client.aclose()

    @log_execution_time("api_gateway.auth_service.request")
    async def _request(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, object],
    ) -> httpx.Response:
        """Выполняет internal Auth HTTP request без логирования payload."""
        try:
            response = await self._client.request(
                method=method,
                url=path,
                json=payload,
                headers=(build_context_headers()),
            )
        except (
            httpx.TimeoutException,
            httpx.TransportError,
        ) as exc:
            raise TemporaryDependencyError(
                "Authentication Service is temporarily unavailable"
            ) from exc

        if response.status_code >= 500:
            raise TemporaryDependencyError("Authentication Service returned server error")

        return response

    @staticmethod
    def _json_object(
        response: httpx.Response,
    ) -> dict[str, Any]:
        """Парсит JSON object или объявляет dependency contract broken."""
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalDependencyError("Authentication Service returned invalid JSON") from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise ExternalDependencyError("Authentication Service returned invalid object")

        return payload

    def _raise_for_business_error(
        self,
        response: httpx.Response,
    ) -> None:
        """Преобразует internal Auth 4xx contract в Gateway application errors."""
        if response.status_code < 400:
            return

        payload = self._json_object(response)

        error = payload.get("error")

        if not isinstance(
            error,
            dict,
        ):
            raise ExternalDependencyError("Authentication Service error contract is invalid")

        code = str(
            error.get(
                "code",
                "",
            )
        )
        message = str(
            error.get(
                "message",
                "Authentication failed",
            )
        )

        if response.status_code == 401:
            raise AuthenticationError(message)

        if response.status_code == 409:
            raise ResourceConflictError(message)

        if response.status_code == 404:
            raise ResourceNotFoundError(message)

        raise ExternalDependencyError(f"Authentication Service error: {code}")

    @staticmethod
    def _parse_auth_session(
        payload: dict[str, Any],
    ) -> AuthSession:
        """Преобразует trusted internal JSON в typed Gateway DTO."""
        try:
            user_payload = payload["user"]

            if not isinstance(
                user_payload,
                dict,
            ):
                raise TypeError("user must be object")

            return AuthSession(
                user=(HttpAuthServiceClient._parse_user(user_payload)),
                session_token=str(payload["session_token"]),
                expires_at=(
                    datetime.fromisoformat(
                        str(payload["expires_at"]).replace(
                            "Z",
                            "+00:00",
                        )
                    )
                ),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise ExternalDependencyError(
                "Authentication Service session response is invalid"
            ) from exc

    @staticmethod
    def _parse_user(
        payload: dict[str, Any],
    ) -> AuthUser:
        """Преобразует internal user JSON в typed Gateway DTO."""
        try:
            return AuthUser(
                id=UUID(str(payload["id"])),
                email=str(payload["email"]),
                created_at=(
                    datetime.fromisoformat(
                        str(payload["created_at"]).replace(
                            "Z",
                            "+00:00",
                        )
                    )
                ),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise ExternalDependencyError(
                "Authentication Service user response is invalid"
            ) from exc
