# services/document-service/src/document_service/domain/exceptions.py

"""Domain/application exceptions Document Service."""


class DocumentError(Exception):
    """Базовая ошибка Document Service."""


class DocumentValidationError(DocumentError):
    """Входные данные либо PDF нарушают bounded contract."""


class ProjectDocumentNotFoundError(DocumentError):
    """Project document не найден внутри ownership scope."""


class ProjectDocumentConflictError(DocumentError):
    """Lifecycle document не допускает запрошенную операцию."""


class DocumentDependencyError(DocumentError):
    """Storage/database/PDF dependency временно недоступна."""
