# services/auth-service/src/auth_service/application/use_cases/register_user.py

"""Use-case регистрации пользователя и первой opaque session."""

from datetime import timedelta
from uuid import uuid4

from plan_validator_common.observability import (
    log_execution_time,
)

from auth_service.application.dto import (
    AuthSessionResult,
    user_to_view,
)
from auth_service.application.ports.clock import Clock
from auth_service.application.ports.security import (
    PasswordHasher,
    SessionTokenManager,
)
from auth_service.application.ports.unit_of_work import (
    AuthUnitOfWorkFactory,
)
from auth_service.domain.email import normalize_email
from auth_service.domain.exceptions import (
    EmailAlreadyRegisteredError,
)
from auth_service.domain.session import AuthSession
from auth_service.domain.user import User


class RegisterUserUseCase:
    """Создаёт User и opaque session в одной transaction."""

    def __init__(
        self,
        *,
        uow_factory: AuthUnitOfWorkFactory,
        password_hasher: PasswordHasher,
        token_manager: SessionTokenManager,
        clock: Clock,
        session_ttl: timedelta,
    ) -> None:
        """Сохраняет application dependencies use-case."""
        self._uow_factory = uow_factory
        self._password_hasher = password_hasher
        self._token_manager = token_manager
        self._clock = clock
        self._session_ttl = session_ttl

    @log_execution_time("auth.register_user")
    async def execute(
        self,
        *,
        email: str,
        password: str,
    ) -> AuthSessionResult:
        """Регистрирует уникального пользователя и выдаёт первую session."""
        normalized_email = normalize_email(email)
        now = self._clock.now()

        async with self._uow_factory() as uow:
            existing_user = await uow.users.get_by_email(normalized_email)

            if existing_user is not None:
                raise EmailAlreadyRegisteredError("Email is already registered")

            user = User(
                id=uuid4(),
                email=normalized_email,
                password_hash=(self._password_hasher.hash_password(password)),
                is_active=True,
                created_at=now,
                updated_at=now,
            )

            issued_token = self._token_manager.issue_token()

            session = AuthSession(
                id=uuid4(),
                user_id=user.id,
                token_hash=(issued_token.token_hash),
                created_at=now,
                expires_at=(now + self._session_ttl),
                revoked_at=None,
            )

            await uow.users.add(user)
            await uow.sessions.add(session)
            await uow.commit()

        return AuthSessionResult(
            user=user_to_view(user),
            session_token=(issued_token.raw_token),
            expires_at=session.expires_at,
        )
