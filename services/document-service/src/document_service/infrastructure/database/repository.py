# services/document-service/src/document_service/infrastructure/database/repository.py

"""SQLAlchemy Project Document repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from document_service.domain.models import DocumentLifecycle, ProjectDocument
from document_service.infrastructure.database.models import ProjectDocumentModel


class SqlAlchemyProjectDocumentRepository:
    """Хранит Project Document metadata в `document` schema."""

    def __init__(self, session: AsyncSession) -> None:
        """Сохраняет transaction-scoped session."""
        self._session = session

    async def add(self, document: ProjectDocument) -> None:
        """Добавляет metadata."""
        self._session.add(self._to_model(document))
        await self._session.flush()

    async def get_for_user(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
    ) -> ProjectDocument | None:
        """Возвращает owner-scoped document."""
        statement = select(ProjectDocumentModel).where(
            ProjectDocumentModel.id == document_id,
            ProjectDocumentModel.user_id == user_id,
        )
        model = await self._session.scalar(statement)
        return self._to_domain(model) if model is not None else None

    async def get_for_user_for_update(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
    ) -> ProjectDocument | None:
        """Возвращает owner-scoped row с lock."""
        statement = (
            select(ProjectDocumentModel)
            .where(
                ProjectDocumentModel.id == document_id,
                ProjectDocumentModel.user_id == user_id,
            )
            .with_for_update()
        )
        model = await self._session.scalar(statement)
        return self._to_domain(model) if model is not None else None

    async def list_for_user(self, user_id: UUID) -> list[ProjectDocument]:
        """Возвращает visible documents пользователя."""
        statement = (
            select(ProjectDocumentModel)
            .where(
                ProjectDocumentModel.user_id == user_id,
                ProjectDocumentModel.lifecycle != DocumentLifecycle.DELETED.value,
            )
            .order_by(ProjectDocumentModel.created_at.desc())
        )
        models = list((await self._session.scalars(statement)).all())
        return [self._to_domain(model) for model in models]

    async def list_cleanup_candidates(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> list[ProjectDocument]:
        """Возвращает delete-pending либо expired active documents."""
        statement = (
            select(ProjectDocumentModel)
            .where(
                or_(
                    ProjectDocumentModel.lifecycle == DocumentLifecycle.DELETE_PENDING.value,
                    (
                        (ProjectDocumentModel.lifecycle == DocumentLifecycle.ACTIVE.value)
                        & (ProjectDocumentModel.expires_at <= now)
                    ),
                )
            )
            .order_by(ProjectDocumentModel.updated_at.asc())
            .limit(limit)
        )
        models = list((await self._session.scalars(statement)).all())
        return [self._to_domain(model) for model in models]

    async def save(self, document: ProjectDocument) -> None:
        """Сохраняет immutable-domain state."""
        statement = (
            update(ProjectDocumentModel)
            .where(ProjectDocumentModel.id == document.id)
            .values(
                selected_pages=list(document.selected_pages),
                lifecycle=document.lifecycle.value,
                cleanup_error=document.cleanup_error,
                updated_at=document.updated_at,
                expires_at=document.expires_at,
            )
        )
        await self._session.execute(statement)
        await self._session.flush()

    @staticmethod
    def _to_model(document: ProjectDocument) -> ProjectDocumentModel:
        """Преобразует domain -> ORM."""
        return ProjectDocumentModel(
            id=document.id,
            user_id=document.user_id,
            original_name=document.original_name,
            storage_key=document.storage_key,
            mime_type=document.mime_type,
            size_bytes=document.size_bytes,
            sha256=document.sha256,
            page_count=document.page_count,
            selected_pages=list(document.selected_pages),
            lifecycle=document.lifecycle.value,
            cleanup_error=document.cleanup_error,
            created_at=document.created_at,
            updated_at=document.updated_at,
            expires_at=document.expires_at,
        )

    @staticmethod
    def _to_domain(model: ProjectDocumentModel) -> ProjectDocument:
        """Преобразует ORM -> domain."""
        return ProjectDocument(
            id=model.id,
            user_id=model.user_id,
            original_name=model.original_name,
            storage_key=model.storage_key,
            mime_type=model.mime_type,
            size_bytes=model.size_bytes,
            sha256=model.sha256,
            page_count=model.page_count,
            selected_pages=tuple(int(page) for page in model.selected_pages),
            lifecycle=DocumentLifecycle(model.lifecycle),
            cleanup_error=model.cleanup_error,
            created_at=model.created_at,
            updated_at=model.updated_at,
            expires_at=model.expires_at,
        )
