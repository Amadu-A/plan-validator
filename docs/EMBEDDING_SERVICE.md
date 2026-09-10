# Embedding Service — Stage 8

## Назначение

Stage 8 добавляет отдельный Embedding Service и dedicated GPU worker для
`Qwen/Qwen3-VL-Embedding-8B`. Тяжёлое embedding-вычисление не публикуется как
прямой HTTP endpoint и выполняется только через RabbitMQ queue
`plan-validator.gpu.embedding`.

HTTP process предоставляет только operational endpoints:

- `GET /health/live`;
- `GET /health/ready`;
- `GET /internal/v1/embedding/runtime`.

## Model cache

Plan Validator повторно использует уже скачанный cache PDRD. Docker volume
`pdrd-validation-ai_multimodal_model_cache` подключается read-only как
`/models/huggingface`.

Runtime работает в offline-режиме (`HF_HUB_OFFLINE=1`,
`TRANSFORMERS_OFFLINE=1`) и загружает checkpoint только из локального snapshot.
Никакой model download в worker job не выполняется.

При переносе проекта на другой сервер имя external volume можно переопределить
через process environment `PLAN_VALIDATOR_EMBEDDING_MODEL_CACHE_VOLUME`. Этот
параметр не является secret и не добавляется в sparse `.env`.

## GPU lifecycle

Одна операция выполняется в следующем порядке:

1. worker получает сообщение из `plan-validator.gpu.embedding`;
2. захватывает project file lease `/var/lock/plan-validator-gpu/gpu.lock`;
3. проверяет доступную системную RAM;
4. проверяет CUDA и ждёт admission threshold свободной VRAM;
5. загружает cached Qwen checkpoint;
6. строит normalized embedding размерности 4096;
7. собирает безопасную telemetry;
8. уничтожает model object и очищает CUDA allocator cache;
9. освобождает GPU lease;
10. публикует RPC response и подтверждает RabbitMQ message.

Worker concurrency фактически равен одному GPU job, RabbitMQ prefetch равен 1.
Lease координирует GPU только между процессами Plan Validator; глобальную
межпроектную координацию он не подменяет.

## Benchmark

Реальный benchmark запускается отдельно:

```bash
./scripts/benchmark-embedding.sh
```

Он проверяет полный путь RabbitMQ → GPU worker → Qwen → RPC response,
размерность 4096, нормализацию vector и сохраняет telemetry в ignored каталоге
`benchmarks/results/`.

Benchmark намеренно не является частью обычного `./scripts/up.sh`, потому что
он загружает 8B checkpoint и занимает GPU.

## Граница Stage 8

Stage 8 не создаёт Qdrant collections, не выполняет chunk indexing и не делает
semantic retrieval. Эти обязанности начинаются на Stage 9.
