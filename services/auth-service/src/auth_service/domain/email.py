# services/auth-service/src/auth_service/domain/email.py

"""Нормализация email identity внутри Authentication domain."""


def normalize_email(email: str) -> str:
    """Возвращает canonical case-insensitive email identity."""
    return email.strip().casefold()
