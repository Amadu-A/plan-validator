# services/context-service/src/context_service/application/use_cases/context_lifecycle.py

"""Use-cases lifecycle временного Project Context и T/PZ metadata."""

from collections.abc import Callable
from datetime import timedelta
from uuid import UUID, uuid4

from plan_validator_common.observability import log_execution_time

from context_service.application.ports.clock import Clock
from context_service.application.ports.unit_of_work import ContextUnitOfWorkFactory
from context_service.domain.exceptions import (
    ContextSourceConflictError,
    ContextValidationError,
    ProjectContextNotFoundError,
)
from context_service.domain.models import (
    ContextSource,
    ContextSourceKind,
    ContextSourceState,
    ProjectContext,
    ProjectContextState,
)

IdentifierFactory = Callable[[], UUID]


class CreateProjectContextUseCase:
    """Создаёт owner-scoped temporary context с конечным TTL."""

    def __init__(
        self,
        *,
        uow_factory: ContextUnitOfWorkFactory,
        clock: Clock,
        ttl_hours: int,
        identifier_factory: IdentifierFactory = uuid4,
    ) -> None:
        """Сохраняет lifecycle dependencies."""
        self._uow_factory = uow_factory
        self._clock = clock
        self._ttl = timedelta(hours=ttl_hours)
        self._identifier_factory = identifier_factory

    @log_execution_time("context.create_project_context")
    async def execute(
        self,
        *,
        user_id: UUID,
    ) -> ProjectContext:
        """Создаёт active context и initial expiration timestamp."""
        now = self._clock.now()
        context = ProjectContext(
            id=self._identifier_factory(),
            user_id=user_id,
            state=ProjectContextState.ACTIVE,
            cleanup_error=None,
            created_at=now,
            updated_at=now,
            expires_at=now + self._ttl,
        )

        async with self._uow_factory() as uow:
            await uow.contexts.add(context)
            await uow.commit()

        return context


class GetProjectContextUseCase:
    """Возвращает context только его владельцу."""

    def __init__(
        self,
        uow_factory: ContextUnitOfWorkFactory,
    ) -> None:
        """Сохраняет Unit of Work factory."""
        self._uow_factory = uow_factory

    async def execute(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
    ) -> ProjectContext:
        """Возвращает context или domain not-found."""
        async with self._uow_factory() as uow:
            context = await uow.contexts.get_for_user(
                user_id=user_id,
                context_id=context_id,
            )

        if context is None:
            raise ProjectContextNotFoundError("Project Context was not found")

        return context


class RegisterContextSourceUseCase:
    """Регистрирует parser-neutral T либо PZ source metadata."""

    def __init__(
        self,
        *,
        uow_factory: ContextUnitOfWorkFactory,
        clock: Clock,
        ttl_hours: int,
        identifier_factory: IdentifierFactory = uuid4,
    ) -> None:
        """Сохраняет lifecycle dependencies."""
        self._uow_factory = uow_factory
        self._clock = clock
        self._ttl = timedelta(hours=ttl_hours)
        self._identifier_factory = identifier_factory

    @log_execution_time("context.register_source")
    async def execute(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
        kind: ContextSourceKind,
        original_name: str,
        source_sha256: str,
    ) -> ContextSource:
        """Создаёт единственный T/PZ source одного context."""
        normalized_name = original_name.strip()

        if not normalized_name:
            raise ContextValidationError("Context source name must not be empty")

        if len(normalized_name) > 512:
            raise ContextValidationError("Context source name must not exceed 512 characters")

        if len(source_sha256) != 64:
            raise ContextValidationError("Context source SHA256 must contain 64 characters")

        now = self._clock.now()

        async with self._uow_factory() as uow:
            context = await uow.contexts.get_for_user_for_update(
                user_id=user_id,
                context_id=context_id,
            )

            if context is None:
                raise ProjectContextNotFoundError("Project Context was not found")

            if context.state is not ProjectContextState.ACTIVE:
                raise ContextSourceConflictError("Project Context is not active")

            existing = await uow.sources.get_for_context_kind(
                user_id=user_id,
                context_id=context_id,
                kind=kind,
            )

            if existing is not None:
                if (
                    existing.original_name == normalized_name
                    and existing.source_sha256 == source_sha256
                    and existing.state is not ContextSourceState.DELETED
                ):
                    return existing

                raise ContextSourceConflictError(
                    f"Project Context already contains source kind {kind.value}"
                )

            source = ContextSource(
                id=self._identifier_factory(),
                context_id=context_id,
                user_id=user_id,
                kind=kind,
                original_name=normalized_name,
                source_sha256=source_sha256,
                state=ContextSourceState.AWAITING_CHUNKS,
                active_fingerprint=None,
                chunk_count=0,
                created_at=now,
                updated_at=now,
            )

            await uow.sources.add(source)
            await uow.contexts.save(
                context.touch(
                    changed_at=now,
                    ttl=self._ttl,
                )
            )
            await uow.commit()

        return source


class RequestProjectContextCleanupUseCase:
    """Сначала делает context невидимым для последующего physical cleanup."""

    def __init__(
        self,
        *,
        uow_factory: ContextUnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        """Сохраняет lifecycle dependencies."""
        self._uow_factory = uow_factory
        self._clock = clock

    @log_execution_time("context.request_cleanup")
    async def execute(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
    ) -> ProjectContext:
        """Фиксирует cleanup_pending идемпотентно."""
        async with self._uow_factory() as uow:
            context = await uow.contexts.get_for_user_for_update(
                user_id=user_id,
                context_id=context_id,
            )

            if context is None:
                raise ProjectContextNotFoundError("Project Context was not found")

            updated = context.request_cleanup(
                changed_at=self._clock.now(),
            )
            await uow.contexts.save(updated)
            await uow.commit()

        return updated
