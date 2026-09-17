<!-- docs/DOCUMENT_SERVICE.md -->

# Document Service — Stage 11 contract

`document-service` владеет основным PDF project document: original lifecycle, page selection,
native extraction, conditional OCR, page rendering и parser-neutral analysis artifacts.

## Execution model

```text
Browser
  -> API Gateway
      -> Document Service
          -> light metadata/read operations          async HTTP request path
          -> page processing
               -> in-process bounded semaphore
               -> PyMuPDF extraction/render
               -> conditional Tesseract OCR
          -> PostgreSQL + filesystem artifacts
```

Stage 11 **не вводит Rabbit/Celery CPU queue заранее**. Несколько пользователей могут работать
одновременно, но число CPU-heavy batches ограничивается `max_concurrent_tasks`, а один request
ограничен `max_pages_per_request`. Durable CPU queue вводится только после benchmark, если
bounded synchronous path не укладывается в latency/fairness budget.

GPU embedding и будущий VLM analysis остаются отдельными GPU-heavy очередями с общим GPU lease.

## Modality policy

Решение принимается на уровне page/fragment, а не extension:

```text
native text достаточен -> TEXT / text_origin=native
native text слабый -> render -> OCR
OCR usable -> TEXT / text_origin=ocr
visual + usable text -> дополнительно MIXED + render reference
нет usable text -> IMAGE + render reference
```

OCR — fallback, а не обязательный preprocessing каждой страницы.

`generated` text origin зарезервирован и обязан быть отличим от source text. Generated caption
не используется как единственное searchable representation картинки/схемы.

## Fragment contract

```text
fragment_id
page_number
modality: text | image | mixed
text_origin: native | ocr | caption | generated | none
text
image_artifact_id
bbox (normalized 0..1)
ocr_confidence
```

## Storage

```text
data/documents/.objects/<user_id>/<document_id>/original.pdf
data/documents/.objects/<user_id>/<document_id>/renders/page-0001.png
data/documents/.objects/<user_id>/<document_id>/analysis/manifest.json
```

Storage keys формирует server. Raw PDF/image bytes не кладутся в RabbitMQ/Qdrant payload.

## Retention

Main project source baseline: 30 дней. Delete lifecycle logical-first и retryable. Processing
artifacts считаются transient; отдельная artifact TTL cleanup будет доведена вместе с runtime
maintenance acceptance.

## Boundary

Document Service не владеет CAD, N/T/U/E policy, Qdrant retrieval, final engineering finding,
callout layout или frontend. DWG/DXF — Stage 12. VLM decision pipeline — Stage 14.
