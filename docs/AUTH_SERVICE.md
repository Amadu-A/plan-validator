<!-- docs/AUTH_SERVICE.md -->

# Authentication Service Plan Validator

Документ описывает Authentication stage Plan Validator.

## Responsibility

`auth-service` владеет только authentication bounded context:

```text
users
password hashes
opaque sessions
registration
login
logout
current-user resolution
```

Он не владеет project files, catalog, Qdrant, Ollama, RabbitMQ workflows или
frontend state.

## Public boundary

Browser не обращается к `auth-service` напрямую.

Public endpoints остаются у API Gateway:

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

Gateway вызывает внутренние endpoints:

```text
POST /internal/v1/auth/register
POST /internal/v1/auth/login
POST /internal/v1/auth/logout
POST /internal/v1/auth/session
```

Raw session token не попадает в public JSON response. Gateway получает его от
auth-service и устанавливает HttpOnly cookie.

## Opaque sessions

JWT в baseline не используется.

Session token:

```text
cryptographically random
URL-safe
stored in browser as HttpOnly cookie
```

Database хранит только:

```text
SHA-256(token)
```

Raw token не сохраняется.

Cookie baseline:

```text
name: plan_validator_session
HttpOnly: true
SameSite: lax
Secure: false in development
Path: /
TTL: 7 days
```

Production deployment обязан включить `Secure=true`.

## Password hashing

Используется:

```text
argon2-cffi 25.1.0
```

Raw password:

```text
не сохраняется
не логируется
не возвращается в response
```

Login при неизвестном email выполняет fake Argon2 verification, чтобы не
создавать очевидную timing-разницу между существующим и отсутствующим user.

## Database ownership

Project PostgreSQL общий физически, но auth-service владеет отдельной schema:

```text
auth
```

Tables:

```text
auth.users
auth.sessions
```

Alembic version table:

```text
auth_alembic_version
```

Это позволяет другим bounded contexts иметь собственные migrations и schema
ownership в той же PostgreSQL instance.

## Migrations

Migration не запускается скрыто внутри application startup.

One-shot service:

```text
auth-migrate
```

Stage check / first-run launcher выполняет:

```bash
docker compose --profile ops run --rm auth-migrate
```

Обычный:

```bash
docker compose up -d --build
```

не выполняет migration side effect.

## Application architecture

```text
Transport
   ↓
Application use-cases
   ↓
Domain

Infrastructure
   └── implements Application ports
```

Repositories разделены:

```text
user_repository.py
session_repository.py
```

SQLAlchemy отсутствует в transport/application/domain.

Transaction boundary принадлежит use-case через `AuthUnitOfWork`.

## Configuration policy

Application configuration не перечисляется длинным `environment:` block в
Compose.

Safe settings:

```text
Pydantic defaults
.env.example
```

Secrets:

```text
sparse .env
```

Auth container получает sparse `.env` через `env_file`, потому что ему нужен
PostgreSQL password. `.env.example` копируется в image и читается самим
Pydantic Settings.

API Gateway не получает project secrets, потому что ему они не нужны.

Compose оставляет только deployment/container wiring:

```text
build
ports/expose
networks
volumes
user
healthcheck
security options
env_file only where secret injection is required
```

Infrastructure images вроде PostgreSQL являются исключением: официальный image
требует `POSTGRES_*` variables и не использует наш Pydantic package.

## Database settings

Safe defaults:

```text
host=postgres
port=5432
database=plan_validator
user=plan_validator
schema=auth
pool_size=10
max_overflow=10
pool_timeout=30s
```

Password:

```text
PLAN_VALIDATOR_POSTGRES_PASSWORD
```

Он остаётся одним из двух project secrets.

## Error semantics

Internal auth service:

```text
email_already_registered -> 409
invalid_credentials      -> 401
invalid_session          -> 401
user_inactive            -> 401
unexpected               -> 500
```

Gateway преобразует internal error contract в public error contract и не
возвращает internal stack trace.

## Session lifecycle

Session states определяются данными:

```text
active
expired
revoked
```

Logout идемпотентный: повторный logout или неизвестный token не создаёт ошибку.

Expired/revoked session cleanup будет подключён к service-owned housekeeping
flow вместе с общим scheduler. До этого auth schema не используется как
источник долгосрочного business history.

## Security boundaries

- auth-service не публикует host port;
- доступен только в project private Docker network;
- container работает non-root;
- filesystem read-only;
- capabilities dropped;
- Docker socket не монтируется;
- password/session token не логируются;
- Gateway cookie HttpOnly;
- raw session token не хранится в PostgreSQL;
- session token не передаётся в URL/query string.

## Runtime flow

Registration:

```text
Browser
 -> Gateway
 -> auth-service
 -> normalize email
 -> ensure unique
 -> Argon2 hash
 -> create user
 -> issue opaque token
 -> store token hash
 -> commit
 -> Gateway sets cookie
```

Login:

```text
Browser
 -> Gateway
 -> auth-service
 -> lookup user
 -> Argon2 verify/fake verify
 -> issue session
 -> commit
 -> Gateway sets cookie
```

Current user:

```text
Browser cookie
 -> Gateway
 -> internal session request
 -> hash raw token
 -> load session
 -> check revoked/expiry
 -> load active user
 -> return user
```

Logout:

```text
Browser cookie
 -> Gateway
 -> auth-service
 -> hash token
 -> revoke session if present
 -> Gateway deletes cookie
```

## Validation

Main stage gate:

```bash
./scripts/check-auth.sh
```

`--fix`:

```text
sync Python dependencies
Ruff auto-fix/format
previous stage immutable checks
unit tests
transport tests
architecture tests
Compose validation
build auth/gateway
Alembic upgrade head
start auth/gateway
database readiness
migration-head check
public runtime auth E2E
structured log check
```

`--check`:

```text
no dependency installation
no formatting
no migration
no rebuild/restart
current runtime health
current migration head
tests
```

## Runtime dependency baseline

```text
FastAPI           0.141.1
Uvicorn           0.52.1
SQLAlchemy        2.0.52
Alembic           1.19.2
Psycopg           3.3.5
argon2-cffi       25.1.0
email-validator   2.3.0
Python image      3.12.14-slim-bookworm
```
