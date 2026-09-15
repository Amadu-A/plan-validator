# services/context-service/Dockerfile
#
# CPU/network runtime временного Project Context и background maintenance.
# GPU embeddings выполняются только shared embedding-worker через RabbitMQ RPC.

FROM python:3.12.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp

WORKDIR /app

COPY .env.example .env.example

COPY packages/common/pyproject.toml packages/common/pyproject.toml
COPY packages/common/src packages/common/src

COPY services/context-service/pyproject.toml services/context-service/pyproject.toml
COPY services/context-service/src services/context-service/src
COPY services/context-service/alembic.ini services/context-service/alembic.ini
COPY services/context-service/migrations services/context-service/migrations

RUN python -m pip install \
    --no-cache-dir \
    ./packages/common \
    ./services/context-service

RUN mkdir -p \
    /app/var/log \
    && chown -R 1000:1000 /app/var

USER 1000:1000

EXPOSE 8000

CMD ["python", "-m", "context_service.main"]