# services/auth-service/src/auth_service/application/use_cases/login_user.py

"""Use-case password login и создания opaque session."""

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
    InvalidCredentialsError,
)
from auth_service.domain.session import AuthSession


class LoginUserUseCase:
    """Проверяет password и выдаёт новую independent session."""

    def __init__(
        self,
        *,
        uow_factory: AuthUnitOfWorkFactory,
        password_hasher: PasswordHasher,
        token_manager: SessionTokenManager,
        clock: Clock,
        session_ttl: timedelta,
    ) -> None:
        """Сохраняет зависимости login use-case."""
        self._uow_factory = uow_factory
        self._password_hasher = password_hasher
        self._token_manager = token_manager
        self._clock = clock
        self._session_ttl = session_ttl

    @log_execution_time("auth.login_user")
    async def execute(
        self,
        *,
        email: str,
        password: str,
    ) -> AuthSessionResult:
        """Аутентифицирует user без раскрытия существования email."""
        normalized_email = normalize_email(email)
        now = self._clock.now()

        async with self._uow_factory() as uow:
            user = await uow.users.get_by_email(normalized_email)

            password_valid = self._password_hasher.verify_password(
                password=password,
                password_hash=(user.password_hash if user is not None else None),
            )

            if user is None or not user.is_active or not password_valid:
                raise InvalidCredentialsError("Invalid email or password")

            if self._password_hasher.needs_rehash(user.password_hash):
                await uow.users.update_password_hash(
                    user_id=user.id,
                    password_hash=(self._password_hasher.hash_password(password)),
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

            await uow.sessions.add(session)
            await uow.commit()

        return AuthSessionResult(
            user=user_to_view(user),
            session_token=(issued_token.raw_token),
            expires_at=session.expires_at,
        )
