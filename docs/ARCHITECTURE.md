<!-- docs/ARCHITECTURE.md -->

# Архитектура Plan Validator

Документ фиксирует границы новой реализации. `PDRD-validation` используется как
reference требований и визуального направления, но legacy code structure не
считается архитектурным контрактом.

## 1. Главный принцип

Микросервис выделяется по cohesive bounded context, а не по количеству роутеров.
Это позволяет избежать двух противоположных проблем:

```text
один огромный backend со всем подряд
```

и

```text
десятки container-per-endpoint сервисов с распределённым монолитом
```

Внутри bounded context файлы дополнительно дробятся по feature/use-case/model.

## 2. Целевые сервисы

### frontend

Отвечает только за browser UI:

- header/logo/auth controls;
- footer;
- sidebar;
- upload workspace;
- source management;
- result visualization;
- SVG overlays для bbox/callouts;
- typed clickable sources.

Browser обращается только к API Gateway.

### api-gateway

Public boundary:

- `/api/v1/...`;
- auth context propagation;
- public DTO contract;
- facade над internal services;
- public content proxy;
- request/correlation IDs;
- единый HTTP error boundary.

Gateway не выполняет SQL чужих bounded contexts и не превращается в новый
монолит orchestration logic.

### auth-service

Владеет:

- users;
- password hashes;
- opaque sessions;
- registration/login/logout/me;
- session revocation.

Базовая модель не требует JWT signing secret. Browser получает random opaque
session token в HttpOnly cookie, а storage хранит только безопасное
представление/hash token.

### document-service

Владеет:

- основными PDF project files;
- page selection;
- text extraction;
- page rendering;
- analysis document artifacts;
- lifecycle собственных временных processing files.

### cad-service

Владеет:

- DXF ingestion;
- DWG -> DXF normalization;
- adapter boundary для КОМПАС conversion;
- CAD geometry extraction;
- нормализованным CAD representation.

### catalog-service

Владеет managed source catalog:

- sections;
- nested categories;
- normative documents `N`;
- user package documents `U`;
- section system prompt;
- managed document lifecycle/outbox.

### context-service

Владеет временным project context:

- Technical Assignment `T`;
- ТЗ extraction/renders;
- временная T vector collection;
- выбранная часть Пояснительной записки;
- временная PZ vector collection;
- expiration/cleanup своих temporary objects.

T и ПЗ не становятся persistent knowledge автоматически.

### embedding-service

Владеет:

- embedding model runtime;
- text/image/mixed embeddings;
- model identity/fingerprint;
- GPU admission;
- project GPU lease integration;
- model cache.

Точная embedding model/dtype/batch policy утверждается после benchmark RTX 3090
24 GiB VRAM + 32 GiB RAM.

### retrieval-service

Владеет vector search contract:

- Qdrant adapters;
- stable managed aliases;
- N/T/U/E typed retrieval;
- exact filters;
- retrieval diagnostics;
- embedding identity compatibility.

Он не меняет semantic role source. `T` не превращается в `N` из-за similarity.

### experience-service

Владеет Базой Опыта `E`:

- experience metadata;
- persisted cases;
- indexing contract;
- experience retrieval;
- правила eligibility/verification для использования E.

### analysis-service

Владеет AI decision pipeline:

- page understanding;
- shared Ollama VLM client;
- requirement checks;
- N/T/U evidence policy;
- finding-local normative enrichment;
- final finding semantics;
- GPU-heavy analysis execution.

### result-service

Владеет presentation-neutral result artifacts:

- normalized bbox;
- leader/callout geometry;
- annotation layout;
- result render metadata;
- exportable result representation.

Frontend рисует интерактивный SVG overlay, а result-service не прожигает
единственную необратимую картинку как единственный source of truth.

## 3. Shared и project infrastructure

Shared stack уже управляет:

```text
Ollama
RabbitMQ
n8n
```

Application containers подключаются к:

```text
ai-shared
```

через external network только если им действительно нужен shared dependency.

Project-specific:

```text
PostgreSQL 16
Qdrant
Celery/application workers
application volumes
GPU coordination volume
```

Project database/vector storage остаются в private project network.

## 4. Dependency direction внутри Python service

Целевой layout:

```text
src/<package>/
├── application/
│   ├── dto/
│   ├── ports/
│   ├── services/
│   └── use_cases/
├── domain/
│   ├── entities/
│   ├── enums/
│   ├── exceptions/
│   └── value_objects/
├── infrastructure/
│   ├── database/
│   │   ├── models/
│   │   └── repositories/
│   ├── messaging/
│   ├── http/
│   └── ...
├── transport/
│   └── http/
│       ├── routers/
│       └── schemas/
├── core/
│   ├── container.py
│   ├── settings.py
│   └── ...
└── main.py
```

Направление:

```text
Transport -> Application -> Domain
Infrastructure -> Application ports
Composition root -> concrete implementations
```

## 5. Router granularity

Запрещён универсальный router, который одновременно обслуживает несколько
несвязанных ресурсов.

Пример для `catalog-service`:

```text
transport/http/routers/
├── health.py
├── sections.py
├── categories.py
├── normative_documents.py
├── user_documents.py
└── system_prompts.py
```

Router отвечает только за transport concerns:

```text
request parsing
schema validation
auth context
use-case invocation
response mapping
```

SQL, Qdrant queries, file processing и LLM calls в router запрещены.

## 6. Repository granularity

Data access разделяется по предметной ответственности.

Пример:

```text
infrastructure/database/
├── models/
│   ├── section.py
│   ├── category.py
│   ├── normative_document.py
│   └── outbox_message.py
└── repositories/
    ├── section.py
    ├── category.py
    ├── normative_document.py
    └── outbox_message.py
```

Не создаётся общий `crud.py` или `repositories.py`, в котором накапливаются
запросы всех таблиц.

## 7. Unit of Work и transaction boundaries

Атомарность принадлежит application use-case, а не HTTP router.

Операции вида:

```text
create metadata
create lifecycle record
create outbox event
```

должны commit/rollback как один use-case, когда этого требует бизнес-инвариант.

SQLAlchemy session не протаскивается в domain или transport logic.

## 8. Очереди

RabbitMQ используется только там, где asynchronous execution действительно
нужно.

Не отправляются в очередь по умолчанию:

```text
login
navigation
обычный GET
CRUD metadata
простые validation operations
лёгкие uploads metadata
```

Кандидаты на queue:

```text
GPU embedding inference
GPU VLM analysis
массовая indexing operation
тяжёлая CPU conversion/render operation, если benchmark это подтвердит
```

Начальный namespace:

```text
plan-validator.gpu.embedding
plan-validator.gpu.analysis
```

CPU-heavy queue добавляется только после измерения, а не заранее.

## 9. GPU coordination

RTX 3090 является shared physical resource.

Project GPU operations используют общий lease path:

```text
/var/lock/plan-validator-gpu/gpu.lock
```

Порядок:

```text
acquire lease
    ↓
check RAM/VRAM admission
    ↓
load/use runtime
    ↓
unload/release runtime resources
    ↓
release lease
```

`nvidia-smi` preflight без lease не считается механизмом координации из-за
TOCTOU race.

Queue worker baseline для одной GPU-heavy queue:

```text
concurrency = 1
prefetch = 1
```

Cross-process lease остаётся обязательным, потому что embedding и analysis могут
жить в разных worker processes.

## 10. n8n

Shared n8n используется для orchestration, но не для хранения business truth.

Workflow namespace:

```text
[PLAN-VALIDATOR] ...
```

n8n переносит typed data между services и управляет bounded retries/status flow,
но не получает право менять N/T/U/E semantic policy.

## 11. Typed source semantics

```text
N = normative requirement
T = Technical Assignment / customer/project requirement
U = user package document
E = verified experience/finalization source
PZ = temporary project context, не evidence type
```

Нормативное утверждение подтверждается `N`. `T` может направлять targeted N
retrieval, но остаётся `T`.

## 12. Frontend layout

Page composition:

```text
header
├── logo
└── registration/authentication controls

body
├── sidebar
│   ├── sections CRUD
│   ├── Technical Assignment
│   ├── normative documents
│   ├── user documents
│   └── system prompt
└── main-container
    ├── main project upload
    ├── CAD upload/conversion
    ├── explanatory-note context controls
    ├── rendered selected sheets + SVG findings overlay
    └── ordered textual findings with clickable sources

footer
```

CSS следует BEM. JS uses stable `data-*` hooks. Один `style.css` остаётся
entrypoint/aggregator, а block/feature styles живут в отдельных файлах.

## 13. Observability

Каждый service пишет structured logs в stdout/stderr и, по project requirement,
в свой bounded rotated file under shared project log root.

Пример runtime layout:

```text
var/log/
├── api-gateway/
├── auth-service/
├── document-service/
├── cad-service/
├── catalog-service/
├── context-service/
├── embedding-service/
├── retrieval-service/
├── experience-service/
├── analysis-service/
└── result-service/
```

Один общий writable `app.log` для всех processes запрещён.

Retention/rotation определены в `docs/RETENTION_POLICY.md`.

## 14. Health model

Каждый HTTP backend предоставляет:

```text
GET /health/live
GET /health/ready
```

`live` проверяет жизнь процесса.

`ready` проверяет минимальный набор обязательных dependencies конкретного
service. Readiness не должна выполнять тяжёлый inference.
