# services/api-gateway/src/api_gateway/infrastructure/http_context.py

"""Общие correlation headers outbound internal HTTP adapters Gateway."""

from plan_validator_common.observability import (
    get_log_context,
)


def build_context_headers() -> dict[str, str]:
    """Создаёт safe correlation/request/job headers текущего context."""
    context = get_log_context()
    headers: dict[str, str] = {}

    if context.correlation_id is not None:
        headers["X-Correlation-ID"] = context.correlation_id

    if context.request_id is not None:
        headers["X-Request-ID"] = context.request_id

    if context.job_id is not None:
        headers["X-Job-ID"] = context.job_id

    return headers
