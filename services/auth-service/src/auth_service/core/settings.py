# services/auth-service/src/auth_service/core/settings.py

"""Pydantic Settings Authentication Service."""

from urllib.parse import quote

from plan_validator_common.settings import (
    CommonSettings,
)
from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    field_validator,
)


class AuthDatabaseSettings(BaseModel):
    """Safe connection/pool settings PostgreSQL auth schema."""

    host: str = Field(
        default="postgres",
        min_length=1,
    )
    port: int = Field(
        default=5432,
        ge=1,
        le=65535,
    )
    database: str = Field(
        default="plan_validator",
        min_length=1,
    )
    user: str = Field(
        default="plan_validator",
        min_length=1,
    )
    schema_name: str = Field(
        default="auth",
        min_length=1,
    )
    pool_size: int = Field(
        default=10,
        ge=1,
    )
    max_overflow: int = Field(
        default=10,
        ge=0,
    )
    pool_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
    )


class AuthSessionSettings(BaseModel):
    """Lifecycle configuration opaque sessions."""

    ttl_seconds: int = Field(
        default=7 * 24 * 60 * 60,
        ge=60,
    )


class AuthSettings(CommonSettings):
    """Объединяет common configuration и Authentication-specific settings."""

    service_name: str = "auth-service"
    service_version: str = "0.1.0"

    postgres_password: SecretStr

    auth_database: AuthDatabaseSettings = Field(
        default_factory=AuthDatabaseSettings,
    )
    auth_session: AuthSessionSettings = Field(
        default_factory=AuthSessionSettings,
    )

    @field_validator("postgres_password")
    @classmethod
    def validate_postgres_password(
        cls,
        value: SecretStr,
    ) -> SecretStr:
        """Не позволяет запустить service с placeholder password."""
        secret = value.get_secret_value()

        if not secret or secret.startswith("CHANGE_ME"):
            raise ValueError("Real PostgreSQL password is required")

        return value

    @property
    def database_url(self) -> str:
        """Собирает SQLAlchemy URL без логирования SecretStr."""
        password = quote(
            self.postgres_password.get_secret_value(),
            safe="",
        )

        user = quote(
            self.auth_database.user,
            safe="",
        )

        database = quote(
            self.auth_database.database,
            safe="",
        )

        return (
            "postgresql+psycopg://"
            f"{user}:{password}"
            f"@{self.auth_database.host}:"
            f"{self.auth_database.port}/"
            f"{database}"
        )


def load_auth_settings() -> AuthSettings:
    """Загружает auth settings через общий layered Pydantic contract."""
    return AuthSettings()
