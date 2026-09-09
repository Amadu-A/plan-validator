<!-- docs/SHARED_ENGINEERING_STANDARD.md -->

# Shared Engineering Standard

Этот документ связывает `plan-validator` с обязательным engineering standard,
который хранится отдельно в `shared_infrasktructure`.

## Почему standard не копируется в этот repository

Полные guideline-файлы намеренно не дублируются. Две копии одного code-style
быстро расходятся и создают спор, какая версия является актуальной.

Source of truth:

```text
Repository: Amadu-A/shared_infrasktructure
Commit:     b21c285228e722a2721a2622233a33183079bc3b
```

Foundation stage фиксирует этот commit для воспроизводимости. Обновление pin
является отдельным осознанным изменением: сначала анализируется diff guideline,
затем адаптируется `plan-validator`.

## Обязательные файлы

Перед архитектурным планом, созданием кода или существенным изменением MUST быть
прочитаны:

```text
docs/LLM_CONTEXT.md
docs/ENGINEERING_GUIDELINES.md
docs/FRONTEND_GUIDELINES.md
docs/INFRASTRUCTURE_INSTRUCTIONS.md
docs/services.yaml
```

Frontend guideline обязателен полностью при любом изменении HTML/CSS/JS/browser
UI.

## Приоритет требований

```text
явные требования пользователя
        ↓
project-specific docs plan-validator
        ↓
pinned shared engineering standard
        ↓
framework defaults
```

Project-specific правило может отклониться от shared guideline только при
явной технической причине, зафиксированной в документации проекта.

## Критические правила, которые нельзя обходить

Backend:

- Transport не содержит SQL и бизнес-оркестрацию.
- Application зависит от ports/contracts, а не concrete adapters.
- Domain не зависит от framework/infrastructure.
- SQLAlchemy находится только в data-access/infrastructure.
- Concrete dependencies собираются в composition root.
- Transaction boundary соответствует use-case.
- Один cohesive repository отвечает за одну предметную область.
- Application/domain exceptions не являются `HTTPException`.

Code style:

- Python 3.12 baseline.
- PEP 8 и Ruff.
- Type hints для public interfaces.
- Относительный путь указывается при демонстрации каждого файла.
- Source/config/script/template документируется на русском языке.
- Каждая функция, метод и класс имеют содержательную русскую документацию.
- God-functions и god-files не принимаются как нормальная структура.

Observability:

- Structured logs.
- Correlation/request/job IDs на релевантных boundaries.
- Reusable timing decorator на значимых service/use-case operations.
- `time.perf_counter()` для duration.
- Один exception — один traceback.
- Secrets и полные пользовательские документы в logs не пишутся.
- Retention logs конечна.

Configuration:

```text
.env.example -> committed baseline
.env         -> sparse private override
process env  -> deployment override
```

Frontend:

- semantic HTML;
- BEM;
- один CSS entrypoint/aggregator;
- CSS по blocks/features;
- JS по common/components/features;
- `data-*` как стабильные JS hooks;
- нет inline `onclick`;
- нет unsafe raw `innerHTML` для недоверенных данных;
- accessibility не ухудшается.

Infrastructure:

- shared Ollama/RabbitMQ/n8n не дублируются;
- container-to-container access использует Docker DNS;
- `ai-shared` остаётся external network shared infrastructure;
- PostgreSQL/Qdrant project-specific по умолчанию;
- secrets не коммитятся;
- health/readiness endpoints обязательны для long-running backend services.

## Проверка обновления standard

Перед изменением pinned commit необходимо:

1. получить новый commit SHA `shared_infrasktructure`;
2. сравнить обязательные guideline-файлы;
3. проверить противоречия с `docs/ARCHITECTURE.md`,
   `docs/DEVELOPMENT_PROCESS.md` и `docs/RETENTION_POLICY.md`;
4. изменить pin в этом файле и README одним commit;
5. прогнать architecture/quality tests.
