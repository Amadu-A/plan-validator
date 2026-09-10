# services/catalog-service/Dockerfile
#
# Runtime image Catalog Service.
# Safe settings читаются из committed `.env.example`.
# Private `.env` не копируется в image.

FROM python:3.12.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp

WORKDIR /app

COPY .env.example .env.example

COPY packages/common/pyproject.toml packages/common/pyproject.toml
COPY packages/common/src packages/common/src

COPY services/catalog-service/pyproject.toml services/catalog-service/pyproject.toml
COPY services/catalog-service/alembic.ini services/catalog-service/alembic.ini
COPY services/catalog-service/migrations services/catalog-service/migrations
COPY services/catalog-service/src services/catalog-service/src

RUN python -m pip install \
    --no-cache-dir \
    ./packages/common \
    ./services/catalog-service \
    && mkdir -p /app/data/uploads/catalog \
    && chown -R 1000:1000 /app/data

USER 1000:1000

EXPOSE 8000

CMD ["python", "-m", "catalog_service.main"]