# services/context-service/src/context_service/infrastructure/database/context_repository.py

"""SQLAlchemy repositories Context registry, sources и recoverable jobs."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    and_,
    delete,
    exists,
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from context_service.domain.models import (
    TERMINAL_JOB_STATES,
    ContextIndexJob,
    ContextIndexJobState,
    ContextSource,
    ContextSourceKind,
    ContextSourceState,
    NormalizedContextChunk,
    ProjectContext,
    ProjectContextState,
)
from context_service.infrastructure.database.models import (
    ContextIndexJobModel,
    ContextSourceModel,
    ProjectContextModel,
)


class SqlAlchemyProjectContextRepository:
    """Хранит temporary Project Context metadata."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """Сохраняет transaction-scoped session."""
        self._session = session

    async def add(
        self,
        context: ProjectContext,
    ) -> None:
        """Добавляет context."""
        self._session.add(self._to_model(context))

        await self._session.flush()

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
    ) -> ProjectContext | None:
        """Возвращает owner-scoped context."""
        statement = select(ProjectContextModel).where(
            ProjectContextModel.id == context_id,
            ProjectContextModel.user_id == user_id,
        )

        model = await self._session.scalar(statement)

        return self._to_domain(model) if model is not None else None

    async def get_for_user_for_update(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
    ) -> ProjectContext | None:
        """Возвращает owner-scoped context с row lock."""
        statement = (
            select(ProjectContextModel)
            .where(
                ProjectContextModel.id == context_id,
                ProjectContextModel.user_id == user_id,
            )
            .with_for_update()
        )

        model = await self._session.scalar(statement)

        return self._to_domain(model) if model is not None else None

    async def list_cleanup_candidates(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> list[ProjectContext]:
        """Находит expired active и retryable cleanup_pending contexts."""
        statement = (
            select(ProjectContextModel)
            .where(
                or_(
                    and_(
                        ProjectContextModel.state == ProjectContextState.ACTIVE.value,
                        ProjectContextModel.expires_at <= now,
                    ),
                    ProjectContextModel.state == ProjectContextState.CLEANUP_PENDING.value,
                )
            )
            .order_by(
                ProjectContextModel.expires_at.asc(),
                ProjectContextModel.updated_at.asc(),
            )
            .limit(limit)
        )

        models = list((await self._session.scalars(statement)).all())

        return [self._to_domain(model) for model in models]

    async def save(
        self,
        context: ProjectContext,
    ) -> None:
        """Сохраняет immutable-domain context."""
        statement = (
            update(ProjectContextModel)
            .where(ProjectContextModel.id == context.id)
            .values(
                user_id=context.user_id,
                state=context.state.value,
                cleanup_error=context.cleanup_error,
                created_at=context.created_at,
                updated_at=context.updated_at,
                expires_at=context.expires_at,
            )
        )

        await self._session.execute(statement)

        await self._session.flush()

    @staticmethod
    def _to_model(
        context: ProjectContext,
    ) -> ProjectContextModel:
        """Преобразует domain context в persistence model."""
        return ProjectContextModel(
            id=context.id,
            user_id=context.user_id,
            state=context.state.value,
            cleanup_error=context.cleanup_error,
            created_at=context.created_at,
            updated_at=context.updated_at,
            expires_at=context.expires_at,
        )

    @staticmethod
    def _to_domain(
        model: ProjectContextModel,
    ) -> ProjectContext:
        """Преобразует persistence model в domain context."""
        return ProjectContext(
            id=model.id,
            user_id=model.user_id,
            state=ProjectContextState(model.state),
            cleanup_error=model.cleanup_error,
            created_at=model.created_at,
            updated_at=model.updated_at,
            expires_at=model.expires_at,
        )


class SqlAlchemyContextSourceRepository:
    """Хранит T/PZ source metadata."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """Сохраняет transaction-scoped session."""
        self._session = session

    async def add(
        self,
        source: ContextSource,
    ) -> None:
        """Добавляет source."""
        self._session.add(self._to_model(source))

        await self._session.flush()

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
    ) -> ContextSource | None:
        """Возвращает owner-scoped source."""
        statement = select(ContextSourceModel).where(
            ContextSourceModel.id == source_id,
            ContextSourceModel.user_id == user_id,
        )

        model = await self._session.scalar(statement)

        return self._to_domain(model) if model is not None else None

    async def get_for_user_for_update(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
    ) -> ContextSource | None:
        """Возвращает owner-scoped source с row lock."""
        statement = (
            select(ContextSourceModel)
            .where(
                ContextSourceModel.id == source_id,
                ContextSourceModel.user_id == user_id,
            )
            .with_for_update()
        )

        model = await self._session.scalar(statement)

        return self._to_domain(model) if model is not None else None

    async def get_for_context_kind(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
        kind: ContextSourceKind,
    ) -> ContextSource | None:
        """Возвращает T/PZ source одного context."""
        statement = select(ContextSourceModel).where(
            ContextSourceModel.user_id == user_id,
            ContextSourceModel.context_id == context_id,
            ContextSourceModel.kind == kind.value,
        )

        model = await self._session.scalar(statement)

        return self._to_domain(model) if model is not None else None

    async def delete_for_context(
        self,
        *,
        context_id: UUID,
    ) -> None:
        """Удаляет temporary source metadata после Context cleanup."""
        statement = delete(ContextSourceModel).where(ContextSourceModel.context_id == context_id)

        await self._session.execute(statement)

        await self._session.flush()

    async def save(
        self,
        source: ContextSource,
    ) -> None:
        """Сохраняет immutable-domain source."""
        statement = (
            update(ContextSourceModel)
            .where(ContextSourceModel.id == source.id)
            .values(
                context_id=source.context_id,
                user_id=source.user_id,
                kind=source.kind.value,
                original_name=source.original_name,
                source_sha256=source.source_sha256,
                state=source.state.value,
                active_fingerprint=source.active_fingerprint,
                chunk_count=source.chunk_count,
                created_at=source.created_at,
                updated_at=source.updated_at,
            )
        )

        await self._session.execute(statement)

        await self._session.flush()

    @staticmethod
    def _to_model(
        source: ContextSource,
    ) -> ContextSourceModel:
        """Преобразует domain source в persistence model."""
        return ContextSourceModel(
            id=source.id,
            context_id=source.context_id,
            user_id=source.user_id,
            kind=source.kind.value,
            original_name=source.original_name,
            source_sha256=source.source_sha256,
            state=source.state.value,
            active_fingerprint=source.active_fingerprint,
            chunk_count=source.chunk_count,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )

    @staticmethod
    def _to_domain(
        model: ContextSourceModel,
    ) -> ContextSource:
        """Преобразует persistence model в domain source."""
        return ContextSource(
            id=model.id,
            context_id=model.context_id,
            user_id=model.user_id,
            kind=ContextSourceKind(model.kind),
            original_name=model.original_name,
            source_sha256=model.source_sha256,
            state=ContextSourceState(model.state),
            active_fingerprint=model.active_fingerprint,
            chunk_count=model.chunk_count,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class SqlAlchemyContextIndexJobRepository:
    """Хранит persistent execution/recovery state indexing jobs."""

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        """Сохраняет transaction-scoped session."""
        self._session = session

    async def add(
        self,
        job: ContextIndexJob,
    ) -> None:
        """Добавляет indexing job."""
        self._session.add(self._to_model(job))

        await self._session.flush()

    async def get(
        self,
        job_id: UUID,
    ) -> ContextIndexJob | None:
        """Возвращает job без lock."""
        statement = select(ContextIndexJobModel).where(ContextIndexJobModel.id == job_id)

        model = await self._session.scalar(statement)

        return self._to_domain(model) if model is not None else None

    async def get_for_update(
        self,
        job_id: UUID,
    ) -> ContextIndexJob | None:
        """Возвращает job с row lock."""
        statement = (
            select(ContextIndexJobModel).where(ContextIndexJobModel.id == job_id).with_for_update()
        )

        model = await self._session.scalar(statement)

        return self._to_domain(model) if model is not None else None

    async def find_open_for_source_fingerprint(
        self,
        *,
        source_id: UUID,
        fingerprint: str,
    ) -> ContextIndexJob | None:
        """Ищет identical non-terminal job для idempotent enqueue."""
        terminal_values = [state.value for state in TERMINAL_JOB_STATES]

        statement = (
            select(ContextIndexJobModel)
            .where(
                ContextIndexJobModel.source_id == source_id,
                ContextIndexJobModel.fingerprint == fingerprint,
                ContextIndexJobModel.state.not_in(terminal_values),
            )
            .order_by(ContextIndexJobModel.created_at.desc())
            .limit(1)
        )

        model = await self._session.scalar(statement)

        return self._to_domain(model) if model is not None else None

    async def list_recoverable(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> list[ContextIndexJob]:
        """Возвращает только lost-publish, due retry, stale-running и expired jobs."""
        terminal_values = [state.value for state in TERMINAL_JOB_STATES]

        undispatched_queued = and_(
            ContextIndexJobModel.state == ContextIndexJobState.QUEUED.value,
            ContextIndexJobModel.dispatched_at.is_(None),
        )

        due_retry = and_(
            ContextIndexJobModel.state == ContextIndexJobState.RETRY_WAIT.value,
            ContextIndexJobModel.dispatched_at.is_(None),
            or_(
                ContextIndexJobModel.next_attempt_at.is_(None),
                ContextIndexJobModel.next_attempt_at <= now,
            ),
        )

        stale_running = and_(
            ContextIndexJobModel.state == ContextIndexJobState.RUNNING.value,
            ContextIndexJobModel.lease_expires_at.is_not(None),
            ContextIndexJobModel.lease_expires_at <= now,
        )

        expired_nonterminal = and_(
            ContextIndexJobModel.state.not_in(terminal_values),
            ContextIndexJobModel.deadline_at <= now,
        )

        statement = (
            select(ContextIndexJobModel)
            .where(
                or_(
                    undispatched_queued,
                    due_retry,
                    stale_running,
                    expired_nonterminal,
                )
            )
            .order_by(ContextIndexJobModel.updated_at.asc())
            .limit(limit)
        )

        models = list((await self._session.scalars(statement)).all())

        return [self._to_domain(model) for model in models]

    async def list_waiting_for_context_for_update(
        self,
        *,
        context_id: UUID,
    ) -> list[ContextIndexJob]:
        """Блокирует только jobs, которые cleanup может отменить до исполнения."""
        waiting_values = (
            ContextIndexJobState.QUEUED.value,
            ContextIndexJobState.RETRY_WAIT.value,
        )

        statement = (
            select(ContextIndexJobModel)
            .where(
                ContextIndexJobModel.context_id == context_id,
                ContextIndexJobModel.state.in_(waiting_values),
            )
            .order_by(ContextIndexJobModel.created_at.asc())
            .with_for_update()
        )

        models = list((await self._session.scalars(statement)).all())

        return [self._to_domain(model) for model in models]

    async def has_open_for_context(
        self,
        *,
        context_id: UUID,
    ) -> bool:
        """Проверяет наличие non-terminal job до physical Qdrant cleanup."""
        terminal_values = [state.value for state in TERMINAL_JOB_STATES]

        statement = select(
            exists().where(
                ContextIndexJobModel.context_id == context_id,
                ContextIndexJobModel.state.not_in(terminal_values),
            )
        )

        return bool(await self._session.scalar(statement))

    async def delete_for_context(
        self,
        *,
        context_id: UUID,
    ) -> None:
        """Удаляет jobs и persisted normalized chunks очищенного context."""
        statement = delete(ContextIndexJobModel).where(
            ContextIndexJobModel.context_id == context_id
        )

        await self._session.execute(statement)

        await self._session.flush()

    async def save(
        self,
        job: ContextIndexJob,
    ) -> None:
        """Сохраняет immutable-domain job state."""
        statement = (
            update(ContextIndexJobModel)
            .where(ContextIndexJobModel.id == job.id)
            .values(
                context_id=job.context_id,
                source_id=job.source_id,
                user_id=job.user_id,
                kind=job.kind.value,
                fingerprint=job.fingerprint,
                correlation_id=job.correlation_id,
                chunks=[chunk.to_payload() for chunk in job.chunks],
                state=job.state.value,
                attempt=job.attempt,
                max_attempts=job.max_attempts,
                deadline_at=job.deadline_at,
                next_attempt_at=job.next_attempt_at,
                dispatched_at=job.dispatched_at,
                lease_owner=job.lease_owner,
                lease_expires_at=job.lease_expires_at,
                last_error=job.last_error,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
        )

        await self._session.execute(statement)

        await self._session.flush()

    @staticmethod
    def _to_model(
        job: ContextIndexJob,
    ) -> ContextIndexJobModel:
        """Преобразует domain job в persistence model."""
        return ContextIndexJobModel(
            id=job.id,
            context_id=job.context_id,
            source_id=job.source_id,
            user_id=job.user_id,
            kind=job.kind.value,
            fingerprint=job.fingerprint,
            correlation_id=job.correlation_id,
            chunks=[chunk.to_payload() for chunk in job.chunks],
            state=job.state.value,
            attempt=job.attempt,
            max_attempts=job.max_attempts,
            deadline_at=job.deadline_at,
            next_attempt_at=job.next_attempt_at,
            dispatched_at=job.dispatched_at,
            lease_owner=job.lease_owner,
            lease_expires_at=job.lease_expires_at,
            last_error=job.last_error,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    @staticmethod
    def _to_domain(
        model: ContextIndexJobModel,
    ) -> ContextIndexJob:
        """Преобразует persistence model в domain job."""
        return ContextIndexJob(
            id=model.id,
            context_id=model.context_id,
            source_id=model.source_id,
            user_id=model.user_id,
            kind=ContextSourceKind(model.kind),
            fingerprint=model.fingerprint,
            correlation_id=model.correlation_id,
            chunks=tuple(NormalizedContextChunk.from_payload(payload) for payload in model.chunks),
            state=ContextIndexJobState(model.state),
            attempt=model.attempt,
            max_attempts=model.max_attempts,
            deadline_at=model.deadline_at,
            next_attempt_at=model.next_attempt_at,
            dispatched_at=model.dispatched_at,
            lease_owner=model.lease_owner,
            lease_expires_at=model.lease_expires_at,
            last_error=model.last_error,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
