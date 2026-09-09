# services/auth-service/Dockerfile
#
# Runtime image Authentication Service.
#
# `.env.example` содержит только committed safe configuration.
# Private `.env` в image не копируется.

FROM python:3.12.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp

WORKDIR /app

COPY .env.example .env.example

COPY packages/common/pyproject.toml packages/common/pyproject.toml
COPY packages/common/src packages/common/src

COPY services/auth-service/pyproject.toml services/auth-service/pyproject.toml
COPY services/auth-service/alembic.ini services/auth-service/alembic.ini
COPY services/auth-service/migrations services/auth-service/migrations
COPY services/auth-service/src services/auth-service/src

RUN python -m pip install \
    --no-cache-dir \
    ./packages/common \
    ./services/auth-service

USER 1000:1000

EXPOSE 8000

CMD ["python", "-m", "auth_service.main"]