# services/document-service/src/document_service/core/settings.py

"""Pydantic settings Document Service и bounded PDF processing policy."""

from pathlib import Path
from urllib.parse import quote

from plan_validator_common.settings import CommonSettings
from pydantic import BaseModel, Field, SecretStr, field_validator


class DocumentDatabaseSettings(BaseModel):
    """PostgreSQL registry settings."""

    host: str = "postgres"
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = "plan_validator"
    user: str = "plan_validator"
    schema_name: str = "document"
    pool_size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    pool_timeout_seconds: float = Field(default=30.0, gt=0)


class DocumentStorageSettings(BaseModel):
    """Bounded local project storage settings."""

    root_dir: Path = Path("data/documents")
    max_upload_bytes: int = Field(default=256 * 1024 * 1024, gt=0)


class DocumentRetentionSettings(BaseModel):
    """Main source retention и maintenance bounds."""

    source_days: int = Field(default=30, ge=1, le=365)
    maintenance_interval_seconds: int = Field(default=60, ge=5, le=3600)
    cleanup_batch_size: int = Field(default=50, ge=1, le=500)


class DocumentProcessingSettings(BaseModel):
    """CPU admission и deterministic modality thresholds."""

    max_concurrent_tasks: int = Field(default=2, ge=1, le=8)
    max_pages_per_request: int = Field(default=16, ge=1, le=128)
    render_dpi: int = Field(default=144, ge=72, le=300)
    native_text_min_chars: int = Field(default=40, ge=1, le=2000)
    visual_area_threshold: float = Field(default=0.30, ge=0.0, le=1.0)
    ocr_enabled: bool = True
    ocr_languages: str = Field(default="rus+eng", min_length=1)
    ocr_timeout_seconds: float = Field(default=30.0, gt=0, le=120.0)


class DocumentSettings(CommonSettings):
    """Объединяет common и Document-specific configuration."""

    service_name: str = "document-service"
    service_version: str = "0.1.0"
    postgres_password: SecretStr
    document_database: DocumentDatabaseSettings = Field(default_factory=DocumentDatabaseSettings)
    document_storage: DocumentStorageSettings = Field(default_factory=DocumentStorageSettings)
    document_retention: DocumentRetentionSettings = Field(default_factory=DocumentRetentionSettings)
    document_processing: DocumentProcessingSettings = Field(
        default_factory=DocumentProcessingSettings
    )

    @field_validator("postgres_password")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        """Запрещает placeholder вместо runtime secret."""
        secret = value.get_secret_value()
        if not secret or secret.startswith("CHANGE_ME"):
            raise ValueError("Real runtime PostgreSQL secret is required")
        return value

    @property
    def database_url(self) -> str:
        """Собирает SQLAlchemy URL без логирования secret."""
        db = self.document_database
        user = quote(db.user, safe="")
        password = quote(self.postgres_password.get_secret_value(), safe="")
        database = quote(db.database, safe="")
        return f"postgresql+psycopg://{user}:{password}@{db.host}:{db.port}/{database}"


def load_document_settings() -> DocumentSettings:
    """Загружает layered Document settings."""
    return DocumentSettings()
