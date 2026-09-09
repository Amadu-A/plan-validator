# services/api-gateway/src/api_gateway/core/container.py

"""Composition root dependencies API Gateway."""

from dataclasses import (
    dataclass,
    field,
)

from api_gateway.application.auth_service import (
    AuthServiceClient,
)
from api_gateway.application.internal_service import (
    InternalServiceClient,
)
from api_gateway.application.system_info import (
    GetSystemInfoUseCase,
)
from api_gateway.core.settings import (
    GatewaySettings,
)
from api_gateway.infrastructure.auth_client import (
    HttpAuthServiceClient,
)
from api_gateway.infrastructure.http_client import (
    HttpInternalServiceClient,
)


@dataclass(slots=True)
class GatewayContainer:
    """Хранит явно собранные process-level dependencies API Gateway."""

    settings: GatewaySettings
    system_info: GetSystemInfoUseCase
    auth_service: AuthServiceClient
    _ready: bool = field(
        default=False,
        init=False,
        repr=False,
    )

    @property
    def is_ready(self) -> bool:
        """Возвращает текущую operational readiness Gateway process."""
        return self._ready

    def mark_ready(self) -> None:
        """Помечает Gateway готовым после успешного application startup."""
        self._ready = True

    def mark_not_ready(self) -> None:
        """Снимает readiness перед shutdown или при startup failure."""
        self._ready = False

    def create_internal_service_client(
        self,
        *,
        base_url: str,
    ) -> InternalServiceClient:
        """Создаёт concrete generic HTTP adapter через composition root."""
        return HttpInternalServiceClient(
            base_url=base_url,
            connect_timeout_seconds=(self.settings.internal_http.connect_timeout_seconds),
            read_timeout_seconds=(self.settings.internal_http.read_timeout_seconds),
        )

    async def aclose(self) -> None:
        """Закрывает owned long-lived downstream HTTP clients."""
        await self.auth_service.aclose()


def build_container(
    settings: GatewaySettings,
) -> GatewayContainer:
    """Собирает Gateway dependencies без скрытых module-level singletons."""
    system_info = GetSystemInfoUseCase(
        service=settings.service_name,
        service_version=(settings.service_version),
        api_version=settings.api_version,
        environment=(settings.environment.value),
    )

    auth_service = HttpAuthServiceClient(
        base_url=(settings.auth_service.base_url),
        connect_timeout_seconds=(settings.internal_http.connect_timeout_seconds),
        read_timeout_seconds=(settings.internal_http.read_timeout_seconds),
    )

    return GatewayContainer(
        settings=settings,
        system_info=system_info,
        auth_service=auth_service,
    )
