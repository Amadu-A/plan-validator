# services/context-service/src/context_service/domain/exceptions.py

"""Domain/application exceptions Context Service."""


class ContextServiceError(RuntimeError):
    """Базовая ошибка bounded context временного Project Context."""


class ContextValidationError(ContextServiceError):
    """Входные данные нарушают Context contract."""


class ProjectContextNotFoundError(ContextServiceError):
    """Project Context отсутствует либо не принадлежит пользователю."""


class ProjectContextConflictError(ContextServiceError):
    """Lifecycle Project Context несовместим с операцией."""


class ContextSourceNotFoundError(ContextServiceError):
    """Временный T/PZ source не найден."""


class ContextSourceConflictError(ContextServiceError):
    """T/PZ source несовместим с текущим lifecycle."""


class ContextIndexJobNotFoundError(ContextServiceError):
    """Persistent Context indexing job не найден."""


class ContextIndexJobConflictError(ContextServiceError):
    """Indexing job не может выполнить запрошенный transition."""


class ContextDependencyError(ContextServiceError):
    """Внешняя dependency временно не выполнила операцию."""


class ContextJobPublishError(ContextDependencyError):
    """RabbitMQ не подтвердил доставку indexing command."""
