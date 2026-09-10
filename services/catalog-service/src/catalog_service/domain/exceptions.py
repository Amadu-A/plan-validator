# services/catalog-service/src/catalog_service/domain/exceptions.py

"""Domain errors пользовательского каталога Plan Validator."""


class CatalogDomainError(Exception):
    """Базовый тип ожидаемых domain errors Catalog Service."""


class SectionNotFoundError(CatalogDomainError):
    """Означает отсутствие section в каталоге конкретного пользователя."""


class InvalidSectionHierarchyError(CatalogDomainError):
    """Означает недопустимую связь parent/child между sections."""


class InvalidCatalogValueError(CatalogDomainError):
    """Означает нарушение ограничений значения Catalog domain."""
