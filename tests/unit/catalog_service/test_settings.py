# tests/unit/catalog_service/test_settings.py

"""Unit tests Catalog Pydantic Settings."""

import pytest
from pydantic import SecretStr, ValidationError

from catalog_service.core.settings import CatalogSettings


def test_catalog_settings_defaults() -> None:
    """Проверяет safe database defaults."""
    settings = CatalogSettings(
        postgres_password=SecretStr("unit-test-secret"),
        _env_file=None,
    )

    assert settings.service_name == "catalog-service"
    assert settings.catalog_database.host == "postgres"
    assert settings.catalog_database.schema_name == "catalog"
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_catalog_settings_reject_placeholder_password() -> None:
    """Не позволяет использовать committed placeholder как secret."""
    with pytest.raises(ValidationError):
        CatalogSettings(
            postgres_password=SecretStr(
                "CHANGE_ME_GENERATED_AUTOMATICALLY"
            ),
            _env_file=None,
        )
