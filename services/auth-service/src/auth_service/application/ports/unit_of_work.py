# services/auth-service/src/auth_service/application/ports/unit_of_work.py

"""Application Unit of Work contract Authentication Service."""

from types import TracebackType
from typing import Protocol, Self

from auth_service.application.ports.session_repository import (
    SessionRepository,
)
from auth_service.application.ports.user_repository import (
    UserRepository,
)


class AuthUnitOfWork(Protocol):
    """Управляет atomic transaction и auth repositories."""

    @property
    def users(self) -> UserRepository:
        """Возвращает repository пользователей текущей transaction."""

    @property
    def sessions(self) -> SessionRepository:
        """Возвращает repository sessions текущей transaction."""

    async def __aenter__(self) -> Self:
        """Открывает transaction scope."""

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Закрывает transaction и выполняет rollback при необходимости."""

    async def commit(self) -> None:
        """Фиксирует atomic use-case transaction."""

    async def rollback(self) -> None:
        """Откатывает текущую transaction."""


class AuthUnitOfWorkFactory(Protocol):
    """Создаёт новый Unit of Work для каждого application use-case."""

    def __call__(self) -> AuthUnitOfWork:
        """Создаёт независимый transaction scope."""
