<!-- docs/INFRASTRUCTURE.md -->

# Infrastructure и Bootstrap Plan Validator

Документ описывает инфраструктуру Этапа 2. Он не описывает ещё не реализованные
application services как работающие.

## 1. Ownership

Shared infrastructure остаётся отдельным lifecycle в repository:

```text
Amadu-A/shared_infrasktructure
```

Она владеет:

```text
Ollama
RabbitMQ
n8n
external Docker network ai-shared
```

`plan-validator` не создаёт собственные копии этих services.

Project-specific infrastructure:

```text
PostgreSQL 16
Qdrant 1.19.0
private Docker network
project volumes
```

## 2. Первый запуск

Канонический first-run launcher:

```bash
./scripts/up.sh
```

Он:

1. автоматически исправляет безопасно исправляемые Ruff/format issues;
2. создаёт sparse `.env`, если его ещё нет;
3. генерирует только два private project secrets;
4. проверяет/поднимает shared infrastructure из её собственного repository;
5. гарантирует наличие `qwen3-vl:8b-instruct` в shared Ollama;
6. создаёт RabbitMQ vhost `/plan-validator`;
7. создаёт/обновляет RabbitMQ user `plan_validator`;
8. проверяет Docker Compose configuration;
9. подтягивает project infrastructure images;
10. запускает project Compose;
11. ждёт health project infrastructure;
12. запускает неизменяющую итоговую проверку.

Обычный повторный lifecycle остаётся совместимым с:

```bash
docker compose up -d --build
```

Однако pure Compose намеренно не владеет созданием external `ai-shared` и
RabbitMQ application credentials. Это обязанности first-run/bootstrap layer.

## 3. Sparse `.env`

Committed:

```text
.env.example
```

Private local:

```text
.env
```

Project `.env` по умолчанию содержит только:

```text
PLAN_VALIDATOR_POSTGRES_PASSWORD=<generated>
PLAN_VALIDATOR_RABBITMQ_PASSWORD=<generated>
```

Остальные безопасные defaults находятся в `.env.example` и `compose.yaml`.

## 4. PostgreSQL

Image:

```text
postgres:16-alpine
```

Container port:

```text
5432
```

Default development host binding:

```text
127.0.0.1:5438
```

Application containers позже будут обращаться по Docker DNS:

```text
postgres:5432
```

Persistent volume:

```text
postgres-data
```

## 5. Qdrant

Pinned image:

```text
qdrant/qdrant:v1.19.0
```

Container ports:

```text
6333 REST
6334 gRPC
```

Default development host bindings:

```text
127.0.0.1:6335 -> 6333
127.0.0.1:6336 -> 6334
```

Application containers позже используют:

```text
http://qdrant:6333
qdrant:6334
```

Persistent volume:

```text
qdrant-data
```

Qdrant telemetry отключена project configuration.

## 6. Networks

Private network:

```text
plan-validator-private
```

На ней находятся PostgreSQL, Qdrant и позже application services, которым нужен
project storage.

External shared network:

```text
ai-shared
```

К ней позже подключаются только services, которым действительно нужны
Ollama/RabbitMQ/n8n.

Project Compose не создаёт `ai-shared`.

## 7. RabbitMQ isolation

Shared RabbitMQ не используется под bootstrap-admin identity приложением.

Project resources:

```text
vhost: /plan-validator
user:  plan_validator
```

Bootstrap выполняется host-side через `rabbitmqctl` внутри shared RabbitMQ
container. Поэтому bootstrap-admin password не копируется в `.env`
`plan-validator`.

Application password берётся из:

```text
PLAN_VALIDATOR_RABBITMQ_PASSWORD
```

Bootstrap идемпотентный:

- существующий vhost не создаётся повторно;
- существующему application user синхронизируется project password;
- permissions повторно приводятся к ожидаемому состоянию;
- после provisioning выполняется authentication check.

## 8. Shared Ollama

Required analysis model:

```text
qwen3-vl:8b-instruct
```

Bootstrap использует штатный script repository `shared_infrasktructure`:

```text
scripts/pull-ollama-model.sh
```

Если модель уже установлена, shared script её не скачивает повторно.

## 9. Logging

На все containers Этапа 2 применяется bounded Docker logging:

```text
driver: local
max-size: 10m
max-file: 5
```

Это защита stdout/stderr container logs от бесконечного роста.

Application file logging:

```text
var/log/<service>/
```

будет реализовано в Common Package после появления application processes.
Его age/size retention уже зафиксирован в `docs/RETENTION_POLICY.md`.

## 10. Volumes и удаление

Persistent:

```text
postgres-data
qdrant-data
```

Обычная остановка:

```bash
docker compose down
```

Запрещено использовать как обычный restart:

```bash
docker compose down -v
```

поскольку `-v` удаляет persistent database/vector storage.

Temporary T/PZ collections не являются отдельными Docker volumes. Их lifecycle
будет реализован на уровне Context Service/Qdrant registry в Этапе 10.

## 11. Health

PostgreSQL:

```text
pg_isready
```

Qdrant:

```text
/readyz
```

Runtime project check дополнительно выполняет реальный HTTP request к Qdrant
через published localhost port.

## 12. Автоматические проверки

Исправляющий режим:

```bash
./scripts/check-infrastructure.sh
```

или явно:

```bash
./scripts/check-infrastructure.sh --fix
```

Он может:

- исправить Ruff/format;
- создать/дополнить missing project secrets;
- поднять shared stack через его repository;
- скачать отсутствующую required Ollama model;
- provision RabbitMQ project vhost/user;
- pull/start project infrastructure;
- выполнить health checks.

Неизменяющий режим:

```bash
./scripts/check-infrastructure.sh --check
```

Он ничего намеренно не исправляет и не создаёт.

## 13. Безопасность

- `.env` не коммитится;
- project password не печатается;
- shared RabbitMQ admin password не копируется;
- databases по умолчанию публикуются только на `127.0.0.1`;
- shared infrastructure управляется через её собственный repository;
- Docker socket не монтируется в application containers;
- project containers не получают host Docker control.

## 14. Следующий этап

После успешного Этапа 2 Common Package добавит:

```text
Pydantic layered settings
structured JSON logging
bounded per-service file logging
correlation IDs
timing decorator
common exceptions
```

Этап 2 не дублирует эту application-level ответственность.
