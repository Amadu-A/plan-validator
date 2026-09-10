# tests/unit/catalog_service/test_settings.py

"""Unit tests Catalog Pydantic Settings."""

from pathlib import Path

import pytest
from catalog_service.core.settings import CatalogSettings
from pydantic import SecretStr, ValidationError


def test_catalog_settings_defaults() -> None:
    """Проверяет safe database и managed source storage defaults."""
    settings = CatalogSettings(
        postgres_password=SecretStr("unit-test-secret"),
        _env_file=None,
    )

    assert settings.service_name == "catalog-service"
    assert settings.catalog_database.host == "postgres"
    assert settings.catalog_database.schema_name == "catalog"
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.catalog_source_storage.root_dir == Path("data/catalog")
    assert settings.catalog_source_storage.max_upload_bytes == 64 * 1024 * 1024


def test_catalog_settings_reject_placeholder_password() -> None:
    """Не позволяет использовать committed placeholder как secret."""
    with pytest.raises(ValidationError):
        CatalogSettings(
            postgres_password=SecretStr("CHANGE_ME_GENERATED_AUTOMATICALLY"),
            _env_file=None,
        )
