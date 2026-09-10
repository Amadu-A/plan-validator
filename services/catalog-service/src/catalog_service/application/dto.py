# services/catalog-service/src/catalog_service/application/dto.py

"""Transport-neutral DTO Catalog application layer."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SystemPromptView:
    """Безопасное представление текущего пользовательского system prompt."""

    user_id: UUID
    prompt: str
    updated_at: datetime | None
