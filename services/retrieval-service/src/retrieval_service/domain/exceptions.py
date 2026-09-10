# services/retrieval-service/src/retrieval_service/domain/exceptions.py

"""Domain/application exceptions Retrieval Service."""


class RetrievalError(RuntimeError):
    """Базовая ошибка bounded context retrieval."""


class RetrievalValidationError(RetrievalError):
    """Входные данные нарушают retrieval contract."""


class RetrievalSourceNotFoundError(RetrievalError):
    """Managed source ещё не зарегистрирован или отсутствует."""


class RetrievalSourceConflictError(RetrievalError):
    """Source lifecycle/hash несовместим с запрошенной операцией."""


class RetrievalDependencyError(RetrievalError):
    """Внешняя dependency временно не выполнила операцию."""


class RetrievalEmbeddingError(RetrievalDependencyError):
    """Embedding RPC завершился ошибкой либо несовместимым ответом."""


class RetrievalVectorStoreError(RetrievalDependencyError):
    """Qdrant operation не завершилась корректно."""
