# services/auth-service/src/auth_service/domain/exceptions.py

"""Domain errors Authentication Service."""


class AuthDomainError(Exception):
    """Базовый тип ожидаемых authentication domain errors."""


class EmailAlreadyRegisteredError(AuthDomainError):
    """Означает попытку повторно зарегистрировать существующий email."""


class InvalidCredentialsError(AuthDomainError):
    """Означает неверную пару email/password без раскрытия причины."""


class InvalidSessionError(AuthDomainError):
    """Означает отсутствующую, revoked или expired opaque session."""


class UserInactiveError(AuthDomainError):
    """Означает запрет authentication для inactive пользователя."""
