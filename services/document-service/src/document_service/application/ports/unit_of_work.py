# services/document-service/src/document_service/application/ports/unit_of_work.py

"""Unit of Work ports Document Service."""

from types import TracebackType
from typing import Protocol

from document_service.application.ports.repositories import ProjectDocumentRepository


class DocumentUnitOfWork(Protocol):
    """Transaction scope metadata Document Service."""

    @property
    def documents(self) -> ProjectDocumentRepository:
        """Возвращает repository."""

    async def __aenter__(self) -> "DocumentUnitOfWork":
        """Открывает transaction scope."""

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Закрывает transaction scope."""

    async def commit(self) -> None:
        """Фиксирует transaction."""


class DocumentUnitOfWorkFactory(Protocol):
    """Создаёт независимые UoW."""

    def __call__(self) -> DocumentUnitOfWork:
        """Создаёт transaction scope."""
