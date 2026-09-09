# tests/unit/auth_service/test_security.py

"""Unit tests real Argon2 и opaque session security adapters."""

from auth_service.infrastructure.security.password_hasher import (
    Argon2PasswordHasher,
)
from auth_service.infrastructure.security.session_tokens import (
    OpaqueSessionTokenManager,
)


def test_argon2_hash_roundtrip_and_unknown_user_fake_verify() -> None:
    """Проверяет real hash verify и безопасный unknown-user path."""
    hasher = Argon2PasswordHasher()

    password_hash = hasher.hash_password("strong-password-123")

    assert hasher.verify_password(
        password="strong-password-123",
        password_hash=password_hash,
    )

    assert not hasher.verify_password(
        password="wrong-password-456",
        password_hash=password_hash,
    )

    assert not hasher.verify_password(
        password="unknown-password",
        password_hash=None,
    )


def test_session_manager_never_uses_raw_token_as_storage_key() -> None:
    """Проверяет random opaque token и deterministic SHA-256 hash."""
    manager = OpaqueSessionTokenManager()

    issued = manager.issue_token()

    assert issued.raw_token
    assert issued.token_hash
    assert issued.raw_token != issued.token_hash
    assert len(issued.token_hash) == 64

    assert manager.hash_token(issued.raw_token) == issued.token_hash
