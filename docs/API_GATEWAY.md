<!-- docs/API_GATEWAY.md -->

# API Gateway Plan Validator

Документ описывает API Gateway, создаваемый на Этапе 4.

## Responsibility

Gateway является единственной публичной backend HTTP boundary для browser UI.

Он отвечает за:

```text
public API versioning
health/live readiness
request/correlation IDs
public error contract
mapping transport schemas
composition root
internal HTTP client baseline
structured request logs
```

Gateway не отвечает за SQL чужих bounded contexts, Qdrant queries, document/CAD
processing, LLM/embedding inference или business storage.

## Public endpoints

Operational endpoints:

```text
GET /health/live
GET /health/ready
```

Версионированный product API:

```text
/api/v1
GET /api/v1/system/info
```

## Health contract

`/health/live` подтверждает жизнь HTTP process.

`/health/ready` подтверждает завершённый startup composition root. На Этапе 4
Gateway ещё не имеет обязательной runtime dependency от PostgreSQL, Qdrant,
Ollama или RabbitMQ, поэтому чужие services в readiness не проверяются.

## Request context

Pure ASGI `RequestContextMiddleware` принимает либо создаёт:

```text
X-Correlation-ID
X-Request-ID
```

Допустимы только bounded безопасные identifiers. Некорректное входящее значение
заменяется новым UUID-compatible identifier.

Identifiers возвращаются в response headers и добавляются в structured logs через
Common Package `ContextVar`.

## Error boundary

Ожидаемые `PlanValidatorError` обрабатываются FastAPI exception mapping.

Неожиданные `Exception` обрабатываются отдельным pure ASGI
`UnhandledExceptionMiddleware`.

Порядок middleware намеренно такой:

```text
RequestContextMiddleware
        ↓
UnhandledExceptionMiddleware
        ↓
FastAPI / ExceptionMiddleware / routers
```

Это сохраняет `correlation_id` на unexpected error path и гарантирует, что
generic 500 response также получает `X-Correlation-ID` и `X-Request-ID`.

Unexpected exception пишет ровно один traceback на HTTP boundary.

Основное mapping:

```text
ResourceNotFoundError       -> 404
ResourceConflictError       -> 409
ApplicationError            -> 400
TemporaryDependencyError    -> 503
ExternalDependencyError     -> 502
ConfigurationError          -> 500
unexpected Exception        -> 500
```

## Request logging

Один request summary:

```text
event=http_request
method=<method>
path=<path without query>
status_code=<status>
duration_ms=<number>
```

Uvicorn access log отключён, чтобы не дублировать JSON request logging.

## Internal HTTP client

Application port:

```text
InternalServiceClient
```

Concrete infrastructure adapter:

```text
HttpInternalServiceClient
```

Adapter использует HTTPX AsyncClient, bounded connect/read timeout, не следует
redirect автоматически, прокидывает correlation/request/job identifiers и
преобразует transport/HTTP failures в common dependency exceptions.

Concrete client создаётся только composition root.

## Source layout

```text
services/api-gateway/
├── Dockerfile
├── pyproject.toml
└── src/
    └── api_gateway/
        ├── __init__.py
        ├── main.py
        ├── application/
        ├── core/
        ├── infrastructure/
        └── transport/
            └── routers/
```

## Dependency direction

```text
transport -> application
core -> application
core -> infrastructure
infrastructure -> application port
```

Application package не импортирует FastAPI, Starlette, HTTPX, SQLAlchemy, Celery
или Qdrant client.

Routers не импортируют concrete infrastructure adapters.

## Logging

Container stdout/stderr ограничены Docker logging policy.

Application log:

```text
var/log/api-gateway/api-gateway.log
```

Common Package обеспечивает size rotation и age retention.

## Runtime

Image baseline:

```text
python:3.12.14-slim-bookworm
```

Gateway работает non-root, с read-only root filesystem, dropped capabilities и
`no-new-privileges`.

Development host binding:

```text
127.0.0.1:8000
```

## Validation

Auto-fix/runtime:

```bash
./scripts/check-gateway.sh
```

Immutable validation:

```bash
./scripts/check-gateway.sh --check
```

До запуска stage script рекомендуется проверять shell syntax:

```bash
bash -n scripts/check-gateway.sh scripts/up.sh
```

## Current version

```text
service package: 0.1.0
public API:      v1
FastAPI:         0.141.1
Uvicorn:         0.52.1
HTTPX:           0.28.1
Python image:    3.12.14-slim-bookworm
```
