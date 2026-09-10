# services/retrieval-service/Dockerfile
#
# CPU/network runtime Retrieval Service и workers.
# Embeddings вычисляются только dedicated embedding-worker через RabbitMQ RPC.

FROM python:3.12.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp

WORKDIR /app

COPY .env.example .env.example

COPY packages/common/pyproject.toml packages/common/pyproject.toml
COPY packages/common/src packages/common/src

COPY services/retrieval-service/pyproject.toml services/retrieval-service/pyproject.toml
COPY services/retrieval-service/src services/retrieval-service/src
COPY services/retrieval-service/alembic.ini services/retrieval-service/alembic.ini
COPY services/retrieval-service/migrations services/retrieval-service/migrations

RUN python -m pip install \
    --no-cache-dir \
    ./packages/common \
    ./services/retrieval-service

RUN mkdir -p \
    /app/var/log \
    && chown -R 1000:1000 /app/var

USER 1000:1000

EXPOSE 8000

CMD ["python", "-m", "retrieval_service.main"]
