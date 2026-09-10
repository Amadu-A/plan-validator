# services/catalog-service/src/catalog_service/application/use_cases/save_system_prompt.py

"""Use-case сохранения singleton system prompt."""

from uuid import UUID

from plan_validator_common.observability import log_execution_time

from catalog_service.application.dto import SystemPromptView
from catalog_service.application.ports.clock import Clock
from catalog_service.application.ports.unit_of_work import CatalogUnitOfWorkFactory
from catalog_service.domain.system_prompt import SystemPrompt, validate_system_prompt


class SaveSystemPromptUseCase:
    """Создаёт либо обновляет пользовательский system prompt."""

    def __init__(
        self,
        *,
        uow_factory: CatalogUnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        """Сохраняет application dependencies."""
        self._uow_factory = uow_factory
        self._clock = clock

    @log_execution_time("catalog.save_system_prompt")
    async def execute(
        self,
        *,
        user_id: UUID,
        prompt: str,
    ) -> SystemPromptView:
        """Сохраняет bounded prompt и возвращает новое состояние."""
        validated_prompt = validate_system_prompt(prompt)
        now = self._clock.now()

        async with self._uow_factory() as uow:
            existing = await uow.system_prompts.get_for_user(user_id)

            value = SystemPrompt(
                user_id=user_id,
                prompt=validated_prompt,
                created_at=existing.created_at if existing is not None else now,
                updated_at=now,
            )

            await uow.system_prompts.save(value)
            await uow.commit()

        return SystemPromptView(
            user_id=user_id,
            prompt=value.prompt,
            updated_at=value.updated_at,
        )
