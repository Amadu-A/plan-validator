# services/auth-service/src/auth_service/application/use_cases/get_current_user.py

"""Use-case разрешения opaque session в authenticated user."""

from plan_validator_common.observability import (
    log_execution_time,
)

from auth_service.application.dto import (
    UserView,
    user_to_view,
)
from auth_service.application.ports.clock import Clock
from auth_service.application.ports.security import (
    SessionTokenManager,
)
from auth_service.application.ports.unit_of_work import (
    AuthUnitOfWorkFactory,
)
from auth_service.domain.exceptions import (
    InvalidSessionError,
    UserInactiveError,
)


class GetCurrentUserUseCase:
    """Разрешает session token без передачи raw token в persistence."""

    def __init__(
        self,
        *,
        uow_factory: AuthUnitOfWorkFactory,
        token_manager: SessionTokenManager,
        clock: Clock,
    ) -> None:
        """Сохраняет зависимости session-resolution use-case."""
        self._uow_factory = uow_factory
        self._token_manager = token_manager
        self._clock = clock

    @log_execution_time("auth.get_current_user")
    async def execute(
        self,
        *,
        session_token: str,
    ) -> UserView:
        """Возвращает active user для valid non-revoked session."""
        token_hash = self._token_manager.hash_token(session_token)

        async with self._uow_factory() as uow:
            session = await uow.sessions.get_by_token_hash(token_hash)

            if session is None or not session.is_valid(now=self._clock.now()):
                raise InvalidSessionError("Session is invalid or expired")

            user = await uow.users.get_by_id(session.user_id)

            if user is None:
                raise InvalidSessionError("Session user does not exist")

            if not user.is_active:
                raise UserInactiveError("User is inactive")

            return user_to_view(user)
