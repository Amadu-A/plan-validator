# tests/unit/common/test_exceptions.py

"""Unit tests минимальной common exception hierarchy."""

from plan_validator_common.exceptions import (
    ApplicationError,
    ExternalDependencyError,
    PlanValidatorError,
    ResourceConflictError,
    ResourceNotFoundError,
    TemporaryDependencyError,
)


def test_application_exceptions_share_project_root() -> None:
    """Проверяет hierarchy application errors без transport dependency."""
    assert issubclass(
        ApplicationError,
        PlanValidatorError,
    )
    assert issubclass(
        ResourceNotFoundError,
        ApplicationError,
    )
    assert issubclass(
        ResourceConflictError,
        ApplicationError,
    )


def test_temporary_dependency_error_is_external_dependency_error() -> None:
    """Проверяет возможность отдельно обрабатывать retryable dependency failures."""
    assert issubclass(
        TemporaryDependencyError,
        ExternalDependencyError,
    )
    assert issubclass(
        ExternalDependencyError,
        PlanValidatorError,
    )
