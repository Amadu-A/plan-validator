<!-- docs/RETRIEVAL_SERVICE.md -->

# Retrieval Service — Stage 9

## Назначение

Stage 9 связывает persistent Catalog sources `N`/`U` с Embedding Service и Qdrant, но не парсит исходные PDF/DOC/DOCX. Нормализованные chunks являются входным контрактом; их production-поставщиком станет Document Service в Stage 11.

## Семантика источников

- `N` — normative source. Только этот тип позднее может подтверждать нормативное нарушение.
- `U` — user-provided project evidence. Источник полезен для контекста, но не является нормативным доказательством.
- N/U search разделены transport-роутами и mandatory Qdrant `kind` filter.
- Каждый поиск также содержит mandatory `user_id` tenant filter и DB-controlled active `version_key` filter.

## Qdrant layout

Используется одна persistent physical collection:

```text
plan_validator_managed_sources_v1
```

и стабильный alias:

```text
plan_validator_managed_sources
```

Payload каждого point содержит:

```text
user_id
kind
section_id
source_id
source_name
source_sha256
fingerprint
version_key
chunk_id
text
page_number
fragment_index
heading
char_start
char_end
```

`user_id` создаётся как tenant keyword index. `kind`, `section_id`, `source_id` и `version_key` имеют exact keyword indexes.

## Crash-safe reindex

Reindex использует immutable generation fingerprint:

```text
source sha256 + model identity + vector dimension + normalized chunks
    ↓
candidate fingerprint
    ↓
Qdrant candidate points
    ↓
PostgreSQL active_fingerprint switch
    ↓
obsolete Qdrant generations cleanup
```

Поиск получает разрешённые `version_key` из PostgreSQL. Поэтому candidate generation до DB commit невидима, а старая generation после DB switch также невидима, даже если её физический cleanup ещё не завершён.

## Delete lifecycle

Catalog создаёт `catalog.source.delete_requested.v1`. Retrieval сначала фиксирует `state=deleted` и очищает `active_fingerprint` в PostgreSQL, после чего удаляет source points в Qdrant. Тем самым source сразу исчезает из search-visible registry, а Qdrant cleanup можно безопасно повторить.

## RabbitMQ

Используются очереди/exchange project vhost `/plan-validator`:

```text
plan-validator.catalog.events
plan-validator.retrieval.catalog-events
plan-validator.retrieval.index
plan-validator.gpu.embedding
```

Catalog transactional outbox публикуется отдельным `catalog-outbox` process. Retrieval worker принимает Catalog lifecycle events и normalized indexing jobs. Embeddings вычисляются только существующим GPU Embedding worker.

## Batch embedding

Stage 8 benchmark показал, что загрузка 8B checkpoint существенно дороже одного encode. Поэтому Stage 9 расширяет Embedding RPC batch-contract: несколько chunk texts обрабатываются внутри одного model-load lifecycle. GPU micro-batch сохраняется `1`, пока отдельный benchmark не докажет безопасность большего значения.

## HTTP API

Operational:

```text
GET /health/live
GET /health/ready
```

Index/status:

```text
POST /internal/v1/retrieval/sources/{source_id}/index
GET  /internal/v1/retrieval/sources/{source_id}/status
```

Typed retrieval:

```text
POST /internal/v1/retrieval/normative/search
POST /internal/v1/retrieval/user/search
```

Search hits возвращают stable Catalog content URL, а не filesystem path:

```text
/api/v1/catalog/normative-documents/<source_id>/content
/api/v1/catalog/user-documents/<source_id>/content
```

## Stage boundary

Stage 9 намеренно не извлекает текст из PDF/DOC/DOCX и не рендерит страницы. До Stage 11 нормализованные chunks могут передаваться только тестовым/internal producer. Document Service позднее станет штатным producer того же контракта без изменения Retrieval indexing architecture.

## Проверка

Обычный gate:

```bash
./scripts/check-retrieval.sh --fix
./scripts/up.sh
./scripts/check-retrieval.sh --check
```

Explicit heavy E2E с реальным Qwen:

```bash
./scripts/benchmark-retrieval.sh
```

Heavy E2E не входит в normal startup.
