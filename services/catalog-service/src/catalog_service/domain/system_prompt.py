# services/catalog-service/src/catalog_service/domain/system_prompt.py

"""Domain rules сохраняемого пользовательского system prompt."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from catalog_service.domain.exceptions import InvalidCatalogValueError

MAX_SYSTEM_PROMPT_LENGTH = 20_000


@dataclass(frozen=True, slots=True)
class SystemPrompt:
    """Представляет сохранённый prompt конкретного пользователя."""

    user_id: UUID
    prompt: str
    created_at: datetime
    updated_at: datetime


def validate_system_prompt(prompt: str) -> str:
    """Проверяет bounded размер пользовательского prompt."""
    if len(prompt) > MAX_SYSTEM_PROMPT_LENGTH:
        raise InvalidCatalogValueError(
            f"System prompt must not exceed {MAX_SYSTEM_PROMPT_LENGTH} characters"
        )

    return prompt
