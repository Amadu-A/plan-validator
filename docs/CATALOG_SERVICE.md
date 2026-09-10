<!-- docs/CATALOG_SERVICE.md -->

# Catalog Service Plan Validator

Этап 6 реализует пользовательский каталог Plan Validator без document storage,
Qdrant, RabbitMQ и background processing.

## Responsibility

Catalog Service владеет:

```text
user sections
nested section hierarchy
section ordering
saved system prompt
```

Он не владеет:

```text
N/U document content
uploads
Qdrant collections
embeddings
ТЗ/ПЗ context
analysis jobs
results
```

Эти обязанности остаются будущим этапам.

## Public API

Browser работает только через API Gateway:

```text
GET    /api/v1/catalog/sections
POST   /api/v1/catalog/sections
PATCH  /api/v1/catalog/sections/{section_id}
DELETE /api/v1/catalog/sections/{section_id}

GET    /api/v1/catalog/system-prompt
PUT    /api/v1/catalog/system-prompt
```

Gateway разрешает opaque session через Authentication Service и передаёт в
Catalog Service только trusted `user_id`.

## Internal API

Catalog Service доступен только по private Docker network:

```text
GET    /internal/v1/catalog/users/{user_id}/sections
POST   /internal/v1/catalog/users/{user_id}/sections
PATCH  /internal/v1/catalog/users/{user_id}/sections/{section_id}
DELETE /internal/v1/catalog/users/{user_id}/sections/{section_id}

GET    /internal/v1/catalog/users/{user_id}/system-prompt
PUT    /internal/v1/catalog/users/{user_id}/system-prompt
```

## Section model

```text
id
user_id
parent_id nullable
title
sort_order
created_at
updated_at
```

`parent_id` создаёт дерево произвольной глубины.

Invariant:

```text
section cannot parent itself
section cannot be moved below its own descendant
parent must belong to same user
```

При удалении parent section дочерние sections удаляются каскадно. Это относится
только к Catalog metadata. На Этапе 7 source-management обязан будет явно
определить безопасное поведение document resources, поэтому текущий Catalog
Service не создаёт и не удаляет documents.

## System prompt

У каждого user максимум одна запись:

```text
user_id primary key
prompt
created_at
updated_at
```

Пустая строка допустима и означает пользовательский override без дополнительного
текста. Размер ограничен application/transport validation.

## Database ownership

Catalog Service владеет PostgreSQL schema:

```text
catalog
```

Tables:

```text
catalog.sections
catalog.system_prompts
```

Alembic version table:

```text
catalog_alembic_version
```

Migration выполняется отдельным one-shot service `catalog-migrate`; startup
Catalog Service не запускает migration автоматически.

## Architecture

```text
Transport
    ↓
Application use-cases / ports
    ↓
Domain

Infrastructure
    └── SQLAlchemy adapters
```

SQLAlchemy запрещён в Application и Domain.

Repositories разделены:

```text
section_repository.py
system_prompt_repository.py
```

Transaction boundary принадлежит use-case через `CatalogUnitOfWork`.

## Configuration

Application configuration остаётся Pydantic-first.

Safe defaults:

```text
Pydantic
.env.example
```

Private secret:

```text
PLAN_VALIDATOR_POSTGRES_PASSWORD
```

Catalog Service получает sparse `.env` через Compose `env_file`, потому что
доступ к PostgreSQL требует project secret.

Compose не повторяет application settings в `environment:`.

## Readiness

```text
GET /health/live
GET /health/ready
```

Readiness выполняет lightweight PostgreSQL `SELECT 1`.

## Observability

Значимые mutations и reads помечены reusable timing decorator:

```text
catalog.list_sections
catalog.create_section
catalog.update_section
catalog.delete_section
catalog.get_system_prompt
catalog.save_system_prompt
api_gateway.catalog_service.request
```

HTTP boundary пишет один structured summary event на request.

File logs:

```text
var/log/catalog-service/catalog-service.log
```

## Security

- Catalog Service не публикует host port.
- Browser не может передать произвольный trusted `user_id` через public API.
- Gateway получает user identity только через opaque Auth session.
- Catalog queries всегда scoped by `user_id`.
- Cross-user parent/section access возвращается как not found.
- Container non-root/read-only/cap-drop/no-new-privileges.
- Docker socket не монтируется.
- PostgreSQL password не логируется.

## Validation

Исправляющий gate:

```bash
./scripts/check-catalog.sh
```

Он выполняет:

```text
dependency synchronization
Ruff fix/format
previous immutable gates
Catalog unit tests
Gateway Catalog transport tests
architecture tests
Compose validation
Catalog/Gateway build
catalog Alembic upgrade head
Catalog/Gateway startup
readiness
migration-head check
non-root check
structured file log check
public runtime Catalog E2E
runtime test data cleanup
```

Immutable:

```bash
./scripts/check-catalog.sh --check
```

не устанавливает packages, не форматирует, не мигрирует, не rebuild/restart и не
запускает mutating E2E.
