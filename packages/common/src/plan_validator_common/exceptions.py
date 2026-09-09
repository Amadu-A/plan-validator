# packages/common/src/plan_validator_common/exceptions.py

"""Минимальная общая hierarchy ошибок Plan Validator."""


class PlanValidatorError(Exception):
    """Базовый marker для ожидаемых project-level ошибок."""


class ConfigurationError(PlanValidatorError):
    """Означает некорректную или неполную runtime configuration."""


class ApplicationError(PlanValidatorError):
    """Базовый тип ожидаемых ошибок application use-case layer."""


class AuthenticationError(ApplicationError):
    """Означает отсутствие или недействительность authentication context."""


class ResourceNotFoundError(ApplicationError):
    """Означает отсутствие требуемого application resource."""


class ResourceConflictError(ApplicationError):
    """Означает конфликт текущего состояния application resource."""


class ExternalDependencyError(PlanValidatorError):
    """Означает отказ внешней infrastructure dependency."""


class TemporaryDependencyError(ExternalDependencyError):
    """Означает потенциально восстанавливаемый временный отказ dependency."""
