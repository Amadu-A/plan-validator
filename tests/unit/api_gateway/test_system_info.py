# tests/unit/api_gateway/test_system_info.py

"""Unit tests application use-case технической информации Gateway."""

from api_gateway.application.system_info import (
    GetSystemInfoUseCase,
)


def test_system_info_use_case_returns_immutable_metadata() -> None:
    """Проверяет transport-neutral result без infrastructure dependencies."""
    use_case = GetSystemInfoUseCase(
        service="api-gateway",
        service_version="0.1.0",
        api_version="v1",
        environment="test",
    )

    result = use_case.execute()

    assert result.service == "api-gateway"
    assert result.service_version == "0.1.0"
    assert result.api_version == "v1"
    assert result.environment == "test"
