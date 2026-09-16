# services/context-service/src/context_service/application/use_cases/cleanup_context.py

"""Logical-first и retry-safe physical cleanup временного Project Context."""

from uuid import UUID

from plan_validator_common.observability import log_execution_time

from context_service.application.ports.clock import Clock
from context_service.application.ports.unit_of_work import (
    ContextUnitOfWorkFactory,
)
from context_service.application.ports.vector_store import (
    ContextVectorStore,
)
from context_service.domain.exceptions import (
    ProjectContextNotFoundError,
)
from context_service.domain.models import (
    ProjectContext,
    ProjectContextState,
)

_CLEANUP_CANCEL_REASON = "project_context_cleanup_requested"


class ListProjectContextCleanupCandidatesUseCase:
    """Находит expired/retryable contexts для bounded maintenance iteration."""

    def __init__(
        self,
        *,
        uow_factory: ContextUnitOfWorkFactory,
        clock: Clock,
        batch_size: int,
    ) -> None:
        """Сохраняет cleanup scan dependencies."""
        self._uow_factory = uow_factory
        self._clock = clock
        self._batch_size = batch_size

    @log_execution_time("context.list_cleanup_candidates")
    async def execute(
        self,
    ) -> tuple[ProjectContext, ...]:
        """Возвращает bounded snapshot cleanup candidates."""
        async with self._uow_factory() as uow:
            contexts = await uow.contexts.list_cleanup_candidates(
                now=self._clock.now(),
                limit=self._batch_size,
            )

        return tuple(contexts)


class FinalizeProjectContextCleanupUseCase:
    """Отменяет waiting jobs и очищает context после завершения RUNNING jobs."""

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
        """Скрывает context, отменяет ожидание и выполняет safe physical cleanup."""
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
                context = context.request_cleanup(
                    changed_at=self._clock.now(),
                )

                await uow.contexts.save(context)

                await uow.commit()

        async with self._uow_factory() as uow:
            waiting_jobs = await uow.jobs.list_waiting_for_context_for_update(
                context_id=context_id,
            )

            if waiting_jobs:
                changed_at = self._clock.now()

                for job in waiting_jobs:
                    canceled = job.cancel(
                        changed_at=changed_at,
                        reason=_CLEANUP_CANCEL_REASON,
                    )
                    await uow.jobs.save(canceled)

            has_open_jobs = await uow.jobs.has_open_for_context(
                context_id=context_id,
            )

            pending: ProjectContext | None = None

            if has_open_jobs:
                pending = await uow.contexts.get_for_user(
                    user_id=user_id,
                    context_id=context_id,
                )

            if waiting_jobs:
                await uow.commit()

            if has_open_jobs:
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
                        error_message=(f"{type(exc).__name__}: {exc}"),
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

            if locked.state is ProjectContextState.CLEANED:
                return locked

            if await uow.jobs.has_open_for_context(context_id=context_id):
                return locked

            await uow.jobs.delete_for_context(context_id=context_id)

            await uow.sources.delete_for_context(context_id=context_id)

            cleaned = locked.mark_cleaned(
                changed_at=self._clock.now(),
            )

            await uow.contexts.save(cleaned)

            await uow.commit()

        return cleaned
