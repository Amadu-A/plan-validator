# services/embedding-service/Dockerfile
#
# Multi-stage runtime Embedding Service.
# API image остаётся лёгким, а GPU worker получает CUDA PyTorch только
# в отдельном target. Model weights никогда не копируются в image.

FROM python:3.12.14-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp

WORKDIR /app

COPY .env.example .env.example

COPY packages/common/pyproject.toml packages/common/pyproject.toml
COPY packages/common/src packages/common/src

COPY services/embedding-service/pyproject.toml services/embedding-service/pyproject.toml
COPY services/embedding-service/src services/embedding-service/src

RUN python -m pip install \
    --no-cache-dir \
    ./packages/common \
    ./services/embedding-service

RUN mkdir -p \
    /app/var/log \
    /var/lock/plan-validator-gpu \
    /models/huggingface \
    && chown -R 1000:1000 \
    /app/var \
    /var/lock/plan-validator-gpu \
    /models

FROM base AS api

USER 1000:1000

EXPOSE 8000

CMD ["python", "-m", "embedding_service.main"]

FROM base AS gpu

RUN python -m pip install \
    --no-cache-dir \
    --timeout 1000 \
    --retries 10 \
    --index-url https://download.pytorch.org/whl/cu128 \
    torch==2.8.0 \
    torchvision==0.23.0

RUN python -m pip install \
    --no-cache-dir \
    --timeout 1000 \
    --retries 10 \
    "./services/embedding-service[gpu]"

ENV HF_HOME=/models/huggingface \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

USER 1000:1000

CMD ["python", "-m", "embedding_service.infrastructure.messaging.worker"]
