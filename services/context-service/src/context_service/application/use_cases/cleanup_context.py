# services/context-service/src/context_service/application/use_cases/cleanup_context.py

"""Logical-first и retry-safe physical cleanup временного Project Context."""

from uuid import UUID

from plan_validator_common.observability import log_execution_time

from context_service.application.ports.clock import Clock
from context_service.application.ports.unit_of_work import ContextUnitOfWorkFactory
from context_service.application.ports.vector_store import ContextVectorStore
from context_service.domain.exceptions import ProjectContextNotFoundError
from context_service.domain.models import ProjectContext, ProjectContextState


class FinalizeProjectContextCleanupUseCase:
    """Удаляет Qdrant только когда context уже скрыт и jobs terminal."""

    def __init__(
        self,
        *,
        uow_factory: ContextUnitOfWorkFactory,
        vector_store: ContextVectorStore,
        clock: Clock,
    ) -> None:
        """Сохраняет cleanup dependencies."""
        self._uow_factory = uow_factory
        self._vector_store = vector_store
        self._clock = clock

    @log_execution_time("context.finalize_cleanup")
    async def execute(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
    ) -> ProjectContext:
        """Физически удаляет collections только после завершения всех jobs."""
        async with self._uow_factory() as uow:
            context = await uow.contexts.get_for_user_for_update(
                user_id=user_id,
                context_id=context_id,
            )
            if context is None:
                raise ProjectContextNotFoundError("Project Context was not found")

            if context.state is ProjectContextState.CLEANED:
                return context

            if context.state is ProjectContextState.ACTIVE:
                context = context.request_cleanup(changed_at=self._clock.now())
                await uow.contexts.save(context)
                await uow.commit()

        async with self._uow_factory() as uow:
            if await uow.jobs.has_open_for_context(context_id=context_id):
                pending = await uow.contexts.get_for_user(
                    user_id=user_id,
                    context_id=context_id,
                )
                if pending is None:
                    raise ProjectContextNotFoundError("Project Context was not found")
                return pending

        try:
            await self._vector_store.delete_context(context_id=context_id)
        except Exception as exc:
            async with self._uow_factory() as uow:
                locked = await uow.contexts.get_for_user_for_update(
                    user_id=user_id,
                    context_id=context_id,
                )
                if locked is not None:
                    failed = locked.mark_cleanup_failed(
                        changed_at=self._clock.now(),
                        error_message=f"{type(exc).__name__}: {exc}",
                    )
                    await uow.contexts.save(failed)
                    await uow.commit()
            raise

        async with self._uow_factory() as uow:
            locked = await uow.contexts.get_for_user_for_update(
                user_id=user_id,
                context_id=context_id,
            )
            if locked is None:
                raise ProjectContextNotFoundError("Project Context was not found")
            cleaned = locked.mark_cleaned(changed_at=self._clock.now())
            await uow.contexts.save(cleaned)
            await uow.commit()
        return cleaned
