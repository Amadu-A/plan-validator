# services/auth-service/src/auth_service/infrastructure/security/password_hasher.py

"""Argon2 implementation PasswordHasher application port."""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)


class Argon2PasswordHasher:
    """Хеширует passwords через Argon2 и выравнивает unknown-user verify path."""

    def __init__(self) -> None:
        """Создаёт Argon2 runtime и process-local dummy hash."""
        self._hasher = PasswordHasher()
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(32))

    def hash_password(
        self,
        password: str,
    ) -> str:
        """Создаёт Argon2 password hash."""
        return self._hasher.hash(password)

    def verify_password(
        self,
        *,
        password: str,
        password_hash: str | None,
    ) -> bool:
        """Проверяет hash или dummy hash при неизвестном email."""
        candidate_hash = password_hash if password_hash is not None else self._dummy_hash

        try:
            return self._hasher.verify(
                candidate_hash,
                password,
            )
        except (
            VerifyMismatchError,
            VerificationError,
            InvalidHashError,
        ):
            return False

    def needs_rehash(
        self,
        password_hash: str,
    ) -> bool:
        """Проверяет актуальность Argon2 parameters сохранённого hash."""
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True
