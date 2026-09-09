# tests/unit/auth_service/test_auth_use_cases.py

"""Unit tests registration/login/session/logout application flows."""

import asyncio
from collections.abc import Coroutine
from datetime import (
    UTC,
    datetime,
    timedelta,
)
from typing import Any

import pytest
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
from auth_service.domain.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidSessionError,
)

from tests.unit.auth_service.fakes import (
    FakePasswordHasher,
    FakeTokenManager,
    FakeUnitOfWorkFactory,
    FixedClock,
)

NOW = datetime(
    2026,
    9,
    9,
    18,
    0,
    tzinfo=UTC,
)


def run_async[T](
    coroutine: Coroutine[Any, Any, T],
) -> T:
    """Запускает unit-test coroutine без отдельного async pytest plugin."""
    return asyncio.run(coroutine)


def build_use_cases() -> tuple[
    FakeUnitOfWorkFactory,
    RegisterUserUseCase,
    LoginUserUseCase,
    LogoutUserUseCase,
    GetCurrentUserUseCase,
]:
    """Собирает auth use-cases поверх общих deterministic fakes."""
    factory = FakeUnitOfWorkFactory()
    password_hasher = FakePasswordHasher()
    token_manager = FakeTokenManager()
    clock = FixedClock(NOW)

    return (
        factory,
        RegisterUserUseCase(
            uow_factory=factory,
            password_hasher=password_hasher,
            token_manager=token_manager,
            clock=clock,
            session_ttl=timedelta(days=7),
        ),
        LoginUserUseCase(
            uow_factory=factory,
            password_hasher=password_hasher,
            token_manager=token_manager,
            clock=clock,
            session_ttl=timedelta(days=7),
        ),
        LogoutUserUseCase(
            uow_factory=factory,
            token_manager=token_manager,
            clock=clock,
        ),
        GetCurrentUserUseCase(
            uow_factory=factory,
            token_manager=token_manager,
            clock=clock,
        ),
    )


def test_register_creates_user_and_only_token_hash_in_storage() -> None:
    """Проверяет registration transaction и отсутствие raw token в storage."""
    (
        factory,
        register,
        _,
        _,
        _,
    ) = build_use_cases()

    result = run_async(
        register.execute(
            email="Ivan@Example.com",
            password="very-strong-password",
        )
    )

    assert result.user.email == "ivan@example.com"
    assert result.session_token == "raw-token-1"

    assert len(factory.users) == 1
    assert "hash:raw-token-1" in factory.sessions
    assert "raw-token-1" not in factory.sessions


def test_duplicate_registration_is_rejected() -> None:
    """Проверяет uniqueness email на application level."""
    (
        _,
        register,
        _,
        _,
        _,
    ) = build_use_cases()

    run_async(
        register.execute(
            email="user@example.com",
            password="password-number-one",
        )
    )

    with pytest.raises(EmailAlreadyRegisteredError):
        run_async(
            register.execute(
                email="USER@example.com",
                password="password-number-two",
            )
        )


def test_login_rejects_unknown_or_wrong_credentials() -> None:
    """Проверяет одинаковую domain error для unknown email и wrong password."""
    (
        _,
        register,
        login,
        _,
        _,
    ) = build_use_cases()

    run_async(
        register.execute(
            email="user@example.com",
            password="correct-password",
        )
    )

    with pytest.raises(InvalidCredentialsError):
        run_async(
            login.execute(
                email="missing@example.com",
                password="anything-here",
            )
        )

    with pytest.raises(InvalidCredentialsError):
        run_async(
            login.execute(
                email="user@example.com",
                password="wrong-password",
            )
        )


def test_session_resolution_and_logout_revoke_flow() -> None:
    """Проверяет current-user flow и invalidation после logout."""
    (
        _,
        register,
        _,
        logout,
        current_user,
    ) = build_use_cases()

    result = run_async(
        register.execute(
            email="user@example.com",
            password="correct-password",
        )
    )

    user = run_async(current_user.execute(session_token=(result.session_token)))

    assert user.id == result.user.id

    run_async(logout.execute(session_token=(result.session_token)))

    with pytest.raises(InvalidSessionError):
        run_async(current_user.execute(session_token=(result.session_token)))
