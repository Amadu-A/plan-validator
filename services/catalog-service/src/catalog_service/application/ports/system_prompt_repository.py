# services/catalog-service/src/catalog_service/application/ports/system_prompt_repository.py

"""Application port persistence пользовательского system prompt."""

from typing import Protocol
from uuid import UUID

from catalog_service.domain.system_prompt import SystemPrompt


class SystemPromptRepository(Protocol):
    """Определяет persistence operations singleton prompt пользователя."""

    async def get_for_user(self, user_id: UUID) -> SystemPrompt | None:
        """Возвращает сохранённый prompt пользователя."""

    async def save(self, prompt: SystemPrompt) -> None:
        """Создаёт либо обновляет singleton prompt."""