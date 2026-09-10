# services/catalog-service/src/catalog_service/application/use_cases/get_system_prompt.py

"""Use-case чтения сохранённого system prompt."""

from uuid import UUID

from plan_validator_common.observability import log_execution_time

from catalog_service.application.dto import SystemPromptView
from catalog_service.application.ports.unit_of_work import CatalogUnitOfWorkFactory


class GetSystemPromptUseCase:
    """Возвращает prompt либо безопасный empty default."""

    def __init__(self, uow_factory: CatalogUnitOfWorkFactory) -> None:
        """Сохраняет Unit of Work factory."""
        self._uow_factory = uow_factory

    @log_execution_time("catalog.get_system_prompt")
    async def execute(self, *, user_id: UUID) -> SystemPromptView:
        """Получает singleton prompt пользователя."""
        async with self._uow_factory() as uow:
            prompt = await uow.system_prompts.get_for_user(user_id)

            if prompt is None:
                return SystemPromptView(
                    user_id=user_id,
                    prompt="",
                    updated_at=None,
                )

            return SystemPromptView(
                user_id=user_id,
                prompt=prompt.prompt,
                updated_at=prompt.updated_at,
            )
