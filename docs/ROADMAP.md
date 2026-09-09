<!-- docs/ROADMAP.md -->

# Зафиксированный Roadmap

Roadmap подтверждён до начала реализации. Нумерация не дробится по ходу без
отдельного архитектурного решения.

## Этапы

1. **Foundation и project contract.** Структура monorepo, engineering standard,
   README, architecture docs, retention policy, root tooling и development rules.
2. **Infrastructure/bootstrap.** Compose, project PostgreSQL/Qdrant, private
   network, `ai-shared`, sparse `.env`, launcher, shared preflight, healthchecks,
   log mounts и startup gates.
3. **Common package.** Settings pattern, structured logging, correlation IDs,
   timing decorator, common exceptions и unit tests.
4. **API Gateway.** Composition root, health endpoints, error boundary, internal
   HTTP clients, router convention и API versioning.
5. **Authentication.** Users, opaque sessions, registration/login/logout/me,
   repositories, UoW, cookies, auth dependencies и tests.
6. **Catalog.** Sections, nested categories, system prompt, отдельные
   models/repositories/use-cases/routers.
7. **N/U source management.** Upload/storage/lifecycle нормативных и
   пользовательских документов, transactional outbox и content API.
8. **Embedding + GPU coordination.** Embedding runtime, model cache, GPU lease,
   RAM/VRAM admission, GPU queue и benchmark RTX 3090.
9. **N/U indexing и retrieval.** Qdrant persistent collections/aliases/fingerprint,
   typed N/U search, exact filters и reindex lifecycle.
10. **Technical Assignment + Project Context.** Временный T lifecycle/retrieval,
    временная ПЗ, per-context collections и cleanup.
11. **Document Service.** PDF parsing, page selection, extraction, rendering и
    analysis artifacts.
12. **CAD Service.** DXF ingestion, DWG->DXF adapter, КОМПАС adapter contract и
    geometry extraction.
13. **Experience Service.** База Опыта E, indexing/retrieval и eligibility rules.
14. **Analysis Service.** Shared Ollama, page understanding, N/T/U policy,
    finding-local retrieval и final findings.
15. **n8n orchestration.** `[PLAN-VALIDATOR]` workflows, state machine,
    retry/idempotency и selective background queues.
16. **Result Service.** bbox, leader lines, callout placement и result artifacts.
17. **Frontend foundation.** Header/auth, footer, sidebar, main workspace,
    semantic HTML, BEM, partials и responsive layout.
18. **Frontend features.** Catalog, ТЗ, ПЗ, uploads, prompt editor и analysis status.
19. **Frontend results.** Sheet renders, SVG bbox/callouts, findings list,
    cross-highlight и clickable typed sources.
20. **Hardening.** Cleanup/retry/idempotency/recovery, backup/restore, security
    boundaries и migration recovery.
21. **Runtime validation.** RAM/VRAM, queue contention, GPU serialization, load,
    functional/E2E и failure injection tests.
22. **Final documentation/DoD.** Полный README, deployment, diagnostics, API map,
    storage/backup diagrams и acceptance checklist.

## Правило изменения roadmap

Изменение ответственности/порядка этапов допустимо только если новая информация
делает текущий план технически некорректным. Причина изменения фиксируется до
кода, а не постфактум.
