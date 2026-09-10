# services/catalog-service/src/catalog_service/infrastructure/database/repositories/system_prompt.py

"""SQLAlchemy implementation SystemPromptRepository."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from catalog_service.domain.system_prompt import SystemPrompt
from catalog_service.infrastructure.database.models.system_prompt import (
    SystemPromptModel,
)


class SqlAlchemySystemPromptRepository:
    """Реализует singleton persistence prompt пользователя."""

    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет transaction-scoped AsyncSession."""
        self._session = session

    async def get_for_user(self, user_id: UUID) -> SystemPrompt | None:
        """Возвращает prompt по user primary key."""
        model = await self._session.get(SystemPromptModel, user_id)

        if model is None:
            return None

        return SystemPrompt(
            user_id=model.user_id,
            prompt=model.prompt,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def save(self, prompt: SystemPrompt) -> None:
        """Создаёт либо обновляет prompt в текущей transaction."""
        model = await self._session.get(SystemPromptModel, prompt.user_id)

        if model is None:
            self._session.add(
                SystemPromptModel(
                    user_id=prompt.user_id,
                    prompt=prompt.prompt,
                    created_at=prompt.created_at,
                    updated_at=prompt.updated_at,
                )
            )
        else:
            model.prompt = prompt.prompt
            model.updated_at = prompt.updated_at

        await self._session.flush()
