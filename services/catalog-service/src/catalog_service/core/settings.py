# services/catalog-service/src/catalog_service/core/settings.py

"""Pydantic Settings Catalog Service и outbox dispatcher."""

from pathlib import Path
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


class CatalogSourceStorageSettings(BaseModel):
    """Safe persistent storage settings managed N/U sources."""

    root_dir: Path = Path("data/catalog")
    max_upload_bytes: int = Field(default=64 * 1024 * 1024, gt=0)


class CatalogBrokerSettings(BaseModel):
    """Safe shared RabbitMQ endpoint Catalog outbox dispatcher."""

    host: str = Field(default="rabbitmq", min_length=1)
    port: int = Field(default=5672, ge=1, le=65535)
    user: str = Field(default="plan_validator", min_length=1)
    virtual_host: str = Field(default="/plan-validator", min_length=1)
    heartbeat_seconds: int = Field(default=60, ge=10, le=600)


class CatalogOutboxSettings(BaseModel):
    """Safe durable event exchange и polling policy."""

    exchange_name: str = Field(default="plan-validator.catalog.events", min_length=1)
    poll_seconds: float = Field(default=1.0, gt=0, le=60)
    failure_backoff_seconds: float = Field(default=5.0, gt=0, le=300)


class CatalogSettings(CommonSettings):
    """Объединяет common и Catalog-specific configuration."""

    service_name: str = "catalog-service"
    service_version: str = "0.1.0"
    postgres_password: SecretStr
    catalog_database: CatalogDatabaseSettings = Field(default_factory=CatalogDatabaseSettings)
    catalog_source_storage: CatalogSourceStorageSettings = Field(
        default_factory=CatalogSourceStorageSettings
    )
    catalog_broker: CatalogBrokerSettings = Field(default_factory=CatalogBrokerSettings)
    catalog_outbox: CatalogOutboxSettings = Field(default_factory=CatalogOutboxSettings)

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
        password = quote(self.postgres_password.get_secret_value(), safe="")
        user = quote(self.catalog_database.user, safe="")
        database = quote(self.catalog_database.database, safe="")

        return (
            "postgresql+psycopg://"
            f"{user}:{password}"
            f"@{self.catalog_database.host}:"
            f"{self.catalog_database.port}/"
            f"{database}"
        )


class CatalogOutboxProcessSettings(CatalogSettings):
    """Расширяет Catalog settings единственным RabbitMQ secret dispatcher."""

    service_name: str = "catalog-outbox"
    rabbitmq_password: SecretStr

    @field_validator("rabbitmq_password")
    @classmethod
    def validate_rabbitmq_password(cls, value: SecretStr) -> SecretStr:
        """Запрещает placeholder вместо реального RabbitMQ password."""
        secret = value.get_secret_value()

        if not secret or secret.startswith("CHANGE_ME"):
            raise ValueError("Real RabbitMQ password is required")

        return value

    @property
    def broker_url(self) -> str:
        """Собирает AMQP URL без логирования credential."""
        user = quote(self.catalog_broker.user, safe="")
        password = quote(self.rabbitmq_password.get_secret_value(), safe="")
        virtual_host = quote(self.catalog_broker.virtual_host, safe="")

        return (
            f"amqp://{user}:{password}@{self.catalog_broker.host}:"
            f"{self.catalog_broker.port}/{virtual_host}"
        )


def load_catalog_settings() -> CatalogSettings:
    """Загружает settings через общий layered environment contract."""
    return CatalogSettings()


def load_catalog_outbox_settings() -> CatalogOutboxProcessSettings:
    """Загружает dispatcher settings с PostgreSQL/RabbitMQ secrets из `.env`."""
    return CatalogOutboxProcessSettings()
