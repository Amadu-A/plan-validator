# services/catalog-service/src/catalog_service/core/settings.py

"""Pydantic Settings Catalog Service."""

from urllib.parse import quote

from plan_validator_common.settings import CommonSettings
from pydantic import BaseModel, Field, SecretStr, field_validator


class CatalogDatabaseSettings(BaseModel):
    """Safe connection/pool settings PostgreSQL Catalog schema."""

    host: str = Field(default="postgres", min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(default="plan_validator", min_length=1)
    user: str = Field(default="plan_validator", min_length=1)
    schema_name: str = Field(default="catalog", min_length=1)
    pool_size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    pool_timeout_seconds: float = Field(default=30.0, gt=0)


class CatalogSettings(CommonSettings):
    """Объединяет common и Catalog-specific configuration."""

    service_name: str = "catalog-service"
    service_version: str = "0.1.0"

    postgres_password: SecretStr

    catalog_database: CatalogDatabaseSettings = Field(
        default_factory=CatalogDatabaseSettings
    )

    @field_validator("postgres_password")
    @classmethod
    def validate_postgres_password(cls, value: SecretStr) -> SecretStr:
        """Запрещает `.env.example` placeholder как реальный password."""
        secret = value.get_secret_value()

        if not secret or secret.startswith("CHANGE_ME"):
            raise ValueError("Real PostgreSQL password is required")

        return value

    @property
    def database_url(self) -> str:
        """Собирает SQLAlchemy URL без логирования password."""
        password = quote(
            self.postgres_password.get_secret_value(),
            safe="",
        )
        user = quote(self.catalog_database.user, safe="")
        database = quote(self.catalog_database.database, safe="")

        return (
            "postgresql+psycopg://"
            f"{user}:{password}"
            f"@{self.catalog_database.host}:"
            f"{self.catalog_database.port}/"
            f"{database}"
        )


def load_catalog_settings() -> CatalogSettings:
    """Загружает settings через общий layered environment contract."""
    return CatalogSettings()
