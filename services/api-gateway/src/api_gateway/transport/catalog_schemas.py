# services/api-gateway/src/api_gateway/transport/catalog_schemas.py

"""Public HTTP schemas Catalog facade API Gateway."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from api_gateway.application.catalog_service import (
    CatalogSection,
    CatalogSystemPrompt,
)


class CreateSectionRequest(BaseModel):
    """Public request создания section."""

    title: str = Field(min_length=1, max_length=200)
    parent_id: UUID | None = None
    sort_order: int = Field(default=0, ge=0)


class UpdateSectionRequest(BaseModel):
    """Public partial update section."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: UUID | None = None
    sort_order: int | None = Field(default=None, ge=0)


class SaveSystemPromptRequest(BaseModel):
    """Public request сохранения system prompt."""

    prompt: str = Field(max_length=20_000)


class SectionResponse(BaseModel):
    """Public representation Catalog section."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    parent_id: UUID | None
    title: str
    sort_order: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_dto(cls, section: CatalogSection) -> "SectionResponse":
        """Преобразует Gateway DTO в public response."""
        return cls(
            id=section.id,
            parent_id=section.parent_id,
            title=section.title,
            sort_order=section.sort_order,
            created_at=section.created_at,
            updated_at=section.updated_at,
        )


class SectionListResponse(BaseModel):
    """Public list container sections."""

    sections: list[SectionResponse]


class SystemPromptResponse(BaseModel):
    """Public saved system prompt."""

    prompt: str
    updated_at: datetime | None

    @classmethod
    def from_dto(
        cls,
        value: CatalogSystemPrompt,
    ) -> "SystemPromptResponse":
        """Преобразует Gateway DTO в public response."""
        return cls(
            prompt=value.prompt,
            updated_at=value.updated_at,
        )
