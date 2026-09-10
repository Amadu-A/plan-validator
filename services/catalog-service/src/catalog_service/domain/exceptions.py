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


class SectionContainsSourcesError(CatalogDomainError):
    """Означает попытку удалить section с живыми managed sources."""


class ManagedSourceNotFoundError(CatalogDomainError):
    """Означает отсутствие N/U source внутри ownership scope пользователя."""


class InvalidManagedSourceUploadError(CatalogDomainError):
    """Означает некорректный формат, имя или размер загружаемого source."""


class ManagedSourceLifecycleConflictError(CatalogDomainError):
    """Означает операцию, запрещённую текущим lifecycle managed source."""


class ManagedSourceStorageUnavailableError(CatalogDomainError):
    """Означает временную недоступность managed source storage."""
