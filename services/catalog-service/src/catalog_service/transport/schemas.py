# services/catalog-service/src/catalog_service/transport/schemas.py

"""Internal HTTP schemas Catalog Service."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from catalog_service.application.dto import SystemPromptView
from catalog_service.domain.section import Section


class CreateSectionRequest(BaseModel):
    """Internal request создания section."""

    title: str = Field(min_length=1, max_length=200)
    parent_id: UUID | None = None
    sort_order: int = Field(default=0, ge=0)


class UpdateSectionRequest(BaseModel):
    """Internal partial update section."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: UUID | None = None
    sort_order: int | None = Field(default=None, ge=0)


class SaveSystemPromptRequest(BaseModel):
    """Internal request сохранения system prompt."""

    prompt: str = Field(max_length=20_000)


class SectionResponse(BaseModel):
    """Internal safe representation section."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    parent_id: UUID | None
    title: str
    sort_order: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, section: Section) -> "SectionResponse":
        """Преобразует Domain Section в HTTP schema."""
        return cls(
            id=section.id,
            parent_id=section.parent_id,
            title=section.title,
            sort_order=section.sort_order,
            created_at=section.created_at,
            updated_at=section.updated_at,
        )


class SectionListResponse(BaseModel):
    """Container списка sections."""

    sections: list[SectionResponse]


class SystemPromptResponse(BaseModel):
    """Internal representation system prompt."""

    prompt: str
    updated_at: datetime | None

    @classmethod
    def from_dto(cls, value: SystemPromptView) -> "SystemPromptResponse":
        """Преобразует application DTO в transport schema."""
        return cls(
            prompt=value.prompt,
            updated_at=value.updated_at,
        )


class ErrorDetail(BaseModel):
    """Stable internal error payload."""

    code: str
    message: str
    correlation_id: str | None


class ErrorResponse(BaseModel):
    """Единый Catalog error envelope."""

    error: ErrorDetail


class HealthResponse(BaseModel):
    """Operational health response."""

    status: str
    service: str
    version: str
