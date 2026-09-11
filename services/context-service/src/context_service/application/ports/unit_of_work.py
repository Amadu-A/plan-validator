# services/context-service/src/context_service/application/ports/unit_of_work.py

"""Application Unit of Work contract Context Service."""

from types import TracebackType
from typing import Protocol, Self

from context_service.application.ports.repositories import (
    ContextIndexJobRepository,
    ContextSourceRepository,
    ProjectContextRepository,
)


class ContextUnitOfWork(Protocol):
    """Управляет transaction и Context repositories."""

    @property
    def contexts(self) -> ProjectContextRepository:
        """Возвращает repository Project Context."""

    @property
    def sources(self) -> ContextSourceRepository:
        """Возвращает repository T/PZ source."""

    @property
    def jobs(self) -> ContextIndexJobRepository:
        """Возвращает repository durable indexing jobs."""

    async def __aenter__(self) -> Self:
        """Открывает transaction scope."""

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Закрывает transaction с rollback при ошибке."""

    async def commit(self) -> None:
        """Фиксирует transaction."""

    async def rollback(self) -> None:
        """Откатывает transaction."""


class ContextUnitOfWorkFactory(Protocol):
    """Создаёт независимый Context Unit of Work."""

    def __call__(self) -> ContextUnitOfWork:
        """Создаёт transaction scope."""
