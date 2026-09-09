# services/auth-service/src/auth_service/infrastructure/security/session_tokens.py

"""Cryptographically secure opaque session token implementation."""

import hashlib
import secrets

from auth_service.application.ports.security import (
    IssuedSessionToken,
)


class OpaqueSessionTokenManager:
    """Создаёт raw URL-safe token и хранит только SHA-256 representation."""

    def issue_token(
        self,
    ) -> IssuedSessionToken:
        """Создаёт новый 384-bit random opaque token."""
        raw_token = secrets.token_urlsafe(48)

        return IssuedSessionToken(
            raw_token=raw_token,
            token_hash=(self.hash_token(raw_token)),
        )

    def hash_token(
        self,
        raw_token: str,
    ) -> str:
        """Возвращает deterministic SHA-256 hex digest token."""
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
