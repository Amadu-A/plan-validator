# services/retrieval-service/src/retrieval_service/application/ports/unit_of_work.py

"""Application Unit of Work contract Retrieval Service."""

from types import TracebackType
from typing import Protocol, Self

from retrieval_service.application.ports.source_index_repository import SourceIndexRepository


class RetrievalUnitOfWork(Protocol):
    """Управляет transaction и Retrieval repositories."""

    @property
    def source_indexes(self) -> SourceIndexRepository:
        """Возвращает source-index repository текущей transaction."""

    async def __aenter__(self) -> Self:
        """Открывает transaction scope."""

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Закрывает transaction с rollback при необходимости."""

    async def commit(self) -> None:
        """Фиксирует transaction."""

    async def rollback(self) -> None:
        """Откатывает текущую transaction."""


class RetrievalUnitOfWorkFactory(Protocol):
    """Создаёт новый Retrieval Unit of Work."""

    def __call__(self) -> RetrievalUnitOfWork:
        """Создаёт независимый transaction scope."""
