# services/auth-service/src/auth_service/application/use_cases/logout_user.py

"""Use-case идемпотентного revoke opaque session."""

from plan_validator_common.observability import (
    log_execution_time,
)

from auth_service.application.ports.clock import Clock
from auth_service.application.ports.security import (
    SessionTokenManager,
)
from auth_service.application.ports.unit_of_work import (
    AuthUnitOfWorkFactory,
)


class LogoutUserUseCase:
    """Отзывает session, не раскрывая факт существования token."""

    def __init__(
        self,
        *,
        uow_factory: AuthUnitOfWorkFactory,
        token_manager: SessionTokenManager,
        clock: Clock,
    ) -> None:
        """Сохраняет зависимости logout use-case."""
        self._uow_factory = uow_factory
        self._token_manager = token_manager
        self._clock = clock

    @log_execution_time("auth.logout_user")
    async def execute(
        self,
        *,
        session_token: str,
    ) -> None:
        """Идемпотентно отзывает session при её наличии."""
        token_hash = self._token_manager.hash_token(session_token)

        async with self._uow_factory() as uow:
            session = await uow.sessions.get_by_token_hash(token_hash)

            if session is None or session.revoked_at is not None:
                return

            await uow.sessions.revoke(
                token_hash=token_hash,
                revoked_at=self._clock.now(),
            )
            await uow.commit()
