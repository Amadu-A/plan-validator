# services/auth-service/src/auth_service/core/container.py

"""Composition root Authentication Service."""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
)

from auth_service.application.use_cases.check_readiness import (
    CheckReadinessUseCase,
)
from auth_service.application.use_cases.get_current_user import (
    GetCurrentUserUseCase,
)
from auth_service.application.use_cases.login_user import (
    LoginUserUseCase,
)
from auth_service.application.use_cases.logout_user import (
    LogoutUserUseCase,
)
from auth_service.application.use_cases.register_user import (
    RegisterUserUseCase,
)
from auth_service.core.settings import (
    AuthSettings,
)
from auth_service.infrastructure.database.engine import (
    create_auth_engine,
    create_auth_session_factory,
)
from auth_service.infrastructure.database.health import (
    SqlAlchemyDatabaseHealthProbe,
)
from auth_service.infrastructure.database.uow import (
    SqlAlchemyAuthUnitOfWorkFactory,
)
from auth_service.infrastructure.security.clock import (
    SystemClock,
)
from auth_service.infrastructure.security.password_hasher import (
    Argon2PasswordHasher,
)
from auth_service.infrastructure.security.session_tokens import (
    OpaqueSessionTokenManager,
)


@dataclass(slots=True)
class AuthContainer:
    """Хранит process-level dependencies Auth Service."""

    settings: AuthSettings
    engine: AsyncEngine
    register_user: RegisterUserUseCase
    login_user: LoginUserUseCase
    logout_user: LogoutUserUseCase
    get_current_user: GetCurrentUserUseCase
    check_readiness: CheckReadinessUseCase

    async def aclose(self) -> None:
        """Освобождает shared database pool при shutdown."""
        await self.engine.dispose()


def build_container(
    settings: AuthSettings,
) -> AuthContainer:
    """Собирает concrete adapters только в composition root."""
    engine = create_auth_engine(settings)
    session_factory = create_auth_session_factory(engine)

    uow_factory = SqlAlchemyAuthUnitOfWorkFactory(session_factory)

    password_hasher = Argon2PasswordHasher()
    token_manager = OpaqueSessionTokenManager()
    clock = SystemClock()

    session_ttl = timedelta(seconds=(settings.auth_session.ttl_seconds))

    return AuthContainer(
        settings=settings,
        engine=engine,
        register_user=RegisterUserUseCase(
            uow_factory=uow_factory,
            password_hasher=password_hasher,
            token_manager=token_manager,
            clock=clock,
            session_ttl=session_ttl,
        ),
        login_user=LoginUserUseCase(
            uow_factory=uow_factory,
            password_hasher=password_hasher,
            token_manager=token_manager,
            clock=clock,
            session_ttl=session_ttl,
        ),
        logout_user=LogoutUserUseCase(
            uow_factory=uow_factory,
            token_manager=token_manager,
            clock=clock,
        ),
        get_current_user=(
            GetCurrentUserUseCase(
                uow_factory=uow_factory,
                token_manager=token_manager,
                clock=clock,
            )
        ),
        check_readiness=(CheckReadinessUseCase(SqlAlchemyDatabaseHealthProbe(session_factory))),
    )
