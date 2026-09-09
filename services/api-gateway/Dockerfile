# services/api-gateway/Dockerfile
#
# Runtime image публичного API Gateway Plan Validator.
#
# Gateway работает без root privileges. Python bytecode отключён, потому что
# container filesystem в runtime read-only, кроме явно смонтированных каталогов.

FROM python:3.12.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp

WORKDIR /app

COPY packages/common/pyproject.toml packages/common/pyproject.toml
COPY packages/common/src packages/common/src

COPY services/api-gateway/pyproject.toml services/api-gateway/pyproject.toml
COPY services/api-gateway/src services/api-gateway/src

RUN python -m pip install \
    --no-cache-dir \
    ./packages/common \
    ./services/api-gateway

USER 1000:1000

EXPOSE 8000

CMD ["python", "-m", "api_gateway.main"]