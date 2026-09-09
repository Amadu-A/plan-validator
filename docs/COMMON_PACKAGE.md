<!-- docs/COMMON_PACKAGE.md -->

# Common Package Plan Validator

Документ описывает общий Python package, созданный на Этапе 3.

## Назначение

`packages/common` содержит только действительно общие технические primitives,
которые безопасно переиспользовать между bounded contexts.

Он не содержит:

```text
business use-cases
SQLAlchemy models
FastAPI routers
Celery tasks
Qdrant queries
Ollama clients
feature-specific DTO
```

## Package layout

```text
packages/common/
├── pyproject.toml
└── src/
    └── plan_validator_common/
        ├── __init__.py
        ├── exceptions.py
        ├── settings.py
        └── observability/
            ├── __init__.py
            ├── correlation.py
            ├── logging.py
            └── timing.py
```

## Settings

`CommonSettings` использует `pydantic-settings` и общий prefix:

```text
PLAN_VALIDATOR_
```

Dotenv baseline:

```text
.env.example
.env
```

Порядок приоритетов:

```text
model defaults
    ↓
.env.example
    ↓
.env
    ↓
process environment
    ↓
explicit init arguments
```

Используется:

```text
env_nested_delimiter="__"
```

Это позволяет будущим service-specific settings вводить вложенную конфигурацию
без изменения общего механизма загрузки.

## Logging

`configure_logging()` настраивает root logger процесса.

Обязательный stdout/stderr формат — JSON Lines.

Каждая запись содержит минимум:

```text
timestamp
level
logger
service
message
```

При наличии context автоматически добавляются:

```text
correlation_id
request_id
job_id
```

Значимые события используют стабильное поле:

```text
event
```

## File logging

По project requirement file logging включён по умолчанию.

Путь:

```text
var/log/<service>/<service>.log
```

Default limits:

```text
20 MiB active file threshold
7 rotated archives
14 days maximum age for rotated archives
```

Используется `RotatingFileHandler`.

Age cleanup касается только rotated files конкретного service:

```text
<service>.log.*
```

Активный `<service>.log` не удаляется age-cleanup процедурой.

Несколько независимых processes не должны писать в один physical file.
Worker/container получает отдельный `service_name`/process identity.

## Sensitive data

Formatter redacts values дополнительных structured fields, если их key содержит
sensitive markers вроде:

```text
password
secret
token
authorization
cookie
api_key
```

Это дополнительная защита, но она не разрешает передавать secrets внутри
готовой строки `message`. Caller по-прежнему обязан не интерполировать секреты в
текст log message.

## Correlation context

Используются Python `ContextVar`, поэтому request/job context изолирован между
async tasks и потоками выполнения, наследующими корректный context.

Доступны:

```text
get_log_context()
bind_log_context()
reset_log_context()
clear_log_context()
scoped_log_context()
new_correlation_id()
```

Transport middleware позже будет создавать/принимать correlation ID и
устанавливать request context.

Queue boundary позже будет переносить correlation/job ID в message headers.

## Timing decorator

Significant operation оформляется явно:

```python
@log_execution_time("catalog.create_section")
def create_section(...):
    ...
```

или для async function:

```python
@log_execution_time("analysis.run")
async def run_analysis(...):
    ...
```

Decorator использует:

```text
time.perf_counter()
```

Success event:

```text
event=operation_timing
operation=<stable name>
duration_ms=<number>
status=success
```

Error event:

```text
event=operation_timing
operation=<stable name>
duration_ms=<number>
status=error
error_type=<exception class>
```

Decorator не пишет traceback. Исключение пробрасывается дальше, а единственный
traceback должен писать подходящий boundary/error-handler.

## Exceptions

Common package предоставляет минимальную общую hierarchy:

```text
PlanValidatorError
├── ConfigurationError
├── ApplicationError
│   ├── ResourceNotFoundError
│   └── ResourceConflictError
└── ExternalDependencyError
    └── TemporaryDependencyError
```

Feature/domain-specific исключения остаются рядом со своим bounded context.

## Version baseline

Этап 3 фиксирует стабильные версии:

```text
Python >=3.12
Pydantic 2.13.5
pydantic-settings 2.15.0
Hatchling 1.32.0
```

## Validation

Исправляющий режим:

```bash
./scripts/check-common.sh
```

Он:

```text
sync dev/common dependencies
Ruff --fix
Ruff format
architecture tests
common unit tests
import smoke test
git diff --check
```

Неизменяющий режим:

```bash
./scripts/check-common.sh --check
```

Он не устанавливает dependencies и не меняет исходники.

## Architecture restriction

Common package не должен импортировать framework/infrastructure-specific
libraries:

```text
fastapi
sqlalchemy
celery
qdrant_client
ollama
```

Иначе общий package превратится в скрытый coupling layer между bounded contexts.
