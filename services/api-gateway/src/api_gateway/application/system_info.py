# services/api-gateway/src/api_gateway/application/system_info.py

"""Application use-case получения технической информации API Gateway."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SystemInfo:
    """Содержит transport-neutral техническую информацию Gateway."""

    service: str
    service_version: str
    api_version: str
    environment: str


class GetSystemInfoUseCase:
    """Возвращает стабильную техническую информацию текущего Gateway process."""

    def __init__(
        self,
        *,
        service: str,
        service_version: str,
        api_version: str,
        environment: str,
    ) -> None:
        """Сохраняет immutable process metadata для последующего чтения."""
        self._system_info = SystemInfo(
            service=service,
            service_version=service_version,
            api_version=api_version,
            environment=environment,
        )

    def execute(self) -> SystemInfo:
        """Возвращает техническую информацию без infrastructure side effects."""
        return self._system_info
