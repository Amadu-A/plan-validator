<!-- docs/INFRASTRUCTURE.md -->

# Infrastructure и Bootstrap Plan Validator

Документ описывает infrastructure/bootstrap contract Plan Validator.

## 1. Ownership

Shared repository:

```text
Amadu-A/shared_infrasktructure
```

владеет:

```text
Ollama
RabbitMQ
n8n
external Docker network ai-shared
```

Project-specific:

```text
PostgreSQL 16
Qdrant 1.19.0
private Docker network
application containers
project volumes
```

`plan-validator` не создаёт duplicate shared Ollama/RabbitMQ/n8n.

## 2. Первый запуск

Канонический first-run launcher:

```bash
./scripts/up.sh
```

Он последовательно выполняет stage-specific исправляющие gates, migrations,
Compose startup и затем immutable validation.

Обычный повторный lifecycle остаётся:

```bash
docker compose up -d --build
```

Pure Compose намеренно не владеет созданием external `ai-shared`,
RabbitMQ application credentials или migration orchestration.

## 3. Configuration ownership

Application configuration принадлежит Pydantic Settings, а не Compose.

Committed safe catalog:

```text
.env.example
```

Private sparse file:

```text
.env
```

Project `.env` содержит только private values:

```text
PLAN_VALIDATOR_POSTGRES_PASSWORD=<generated>
PLAN_VALIDATOR_RABBITMQ_PASSWORD=<generated>
```

Приоритет application settings:

```text
Pydantic defaults
    ↓
.env.example
    ↓
.env / process environment where the service receives secrets
    ↓
explicit runtime overrides
```

### Что не делаем

Для application services не создаются огромные Compose-блоки:

```yaml
environment:
  PLAN_VALIDATOR_FOO: ...
  PLAN_VALIDATOR_BAR: ...
  PLAN_VALIDATOR_BAZ: ...
```

если эти values уже являются Pydantic/default `.env.example` configuration.

### Что остаётся в Compose

Compose отвечает за deployment/container wiring:

```text
build/image
container user
ports/expose
networks
volumes
depends_on
healthcheck
read_only/tmpfs
security_opt/cap_drop
logging driver
env_file для минимальной передачи secrets, когда service действительно их использует
```

Infrastructure images являются отдельным случаем. Например PostgreSQL не знает
о нашем Pydantic package и требует штатные `POSTGRES_*` environment variables.

## 4. `.env.example` внутри application images

Application Dockerfile копирует committed `.env.example` в working directory.

Это позволяет Pydantic Settings внутри container читать safe baseline напрямую,
не заставляя Compose повторять каждую application variable.

Private `.env` никогда не копируется в image.

Service, которому нужен secret, может получить sparse `.env` через Compose
`env_file`. Service, которому secrets не нужны, sparse `.env` не получает.

## 5. PostgreSQL

Image:

```text
postgres:16-alpine
```

Default host binding:

```text
127.0.0.1:5438
```

Container DNS:

```text
postgres:5432
```

Persistent volume:

```text
postgres-data
```

Application bounded contexts используют отдельные schemas и отдельные migration
version tables.

## 6. Qdrant

Pinned image:

```text
qdrant/qdrant:v1.19.0
```

Host bindings:

```text
127.0.0.1:6335 -> REST 6333
127.0.0.1:6336 -> gRPC 6334
```

Persistent volume:

```text
qdrant-data
```

Qdrant telemetry отключена.

## 7. Networks

Private:

```text
plan-validator-private
```

Shared external:

```text
ai-shared
```

К `ai-shared` подключаются только services, которым реально нужны shared
Ollama/RabbitMQ/n8n.

## 8. RabbitMQ isolation

Project resources:

```text
vhost: /plan-validator
user:  plan_validator
```

Bootstrap выполняется host-side через `rabbitmqctl` внутри shared broker.

Application password:

```text
PLAN_VALIDATOR_RABBITMQ_PASSWORD
```

Shared bootstrap-admin credentials в project `.env` не копируются.

## 9. Shared Ollama

Required analysis model:

```text
qwen3-vl:8b-instruct
```

Модель проверяется/подтягивается через штатный shared script:

```text
scripts/pull-ollama-model.sh
```

## 10. Logging

Docker stdout/stderr:

```text
driver: local
max-size: 10m
max-file: 5
```

Application file logging:

```text
var/log/<service>/<service>.log
```

Common Package обеспечивает size rotation и age cleanup.

Bind mount project runtime log root:

```text
./var/log:/app/var/log
```

не требует дублировать `PLAN_VALIDATOR_LOG_ROOT_DIR` в Compose.

## 11. Volumes и удаление

Persistent:

```text
postgres-data
qdrant-data
```

Обычная остановка:

```bash
docker compose down
```

Не использовать как обычный restart:

```bash
docker compose down -v
```

`-v` удаляет persistent database/vector storage.

Temporary T/PZ/vector lifecycle реализуется service-owned cleanup use-cases, а
не удалением Docker volumes по возрасту.

## 12. Migrations

Migration ownership принадлежит bounded context.

One-shot migration containers используют profile:

```text
ops
```

Обычный `docker compose up` не должен неожиданно выполнять migrations.

First-run/stage scripts выполняют migrations явно до readiness проверки
соответствующего service.

## 13. Health

Infrastructure:

```text
PostgreSQL -> pg_isready
Qdrant     -> /readyz
```

Application:

```text
GET /health/live
GET /health/ready
```

Readiness проверяет только обязательные dependencies данного process.

## 14. Security

- `.env` не коммитится;
- project secrets не печатаются;
- private `.env` не копируется в Docker images;
- service без необходимости не получает чужие secrets;
- application containers работают non-root;
- Docker socket не монтируется;
- filesystem по возможности read-only;
- capabilities dropped;
- project databases публикуются только на localhost в development;
- shared infrastructure управляется своим repository.

## 15. Автоматические проверки

Исправляющие scripts имеют default `--fix`.

CI/final validation использует:

```text
--check
```

`--check` не должен:

```text
форматировать source
ставить packages
создавать secrets
выполнять migrations
rebuild/restart containers
```

Он может выполнять read-only health, schema-head и runtime diagnostics.
