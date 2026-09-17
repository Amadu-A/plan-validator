# services/document-service/Dockerfile

FROM python:3.12.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

COPY .env.example .env.example
COPY packages/common/pyproject.toml packages/common/pyproject.toml
COPY packages/common/src packages/common/src
COPY services/document-service/pyproject.toml services/document-service/pyproject.toml
COPY services/document-service/src services/document-service/src
COPY services/document-service/alembic.ini services/document-service/alembic.ini
COPY services/document-service/migrations services/document-service/migrations

RUN python -m pip install --no-cache-dir ./packages/common ./services/document-service

RUN mkdir -p /app/var/log /app/data/documents \
    && chown -R 1000:1000 /app/var /app/data/documents

USER 1000:1000
EXPOSE 8000
CMD ["python", "-m", "document_service.main"]
