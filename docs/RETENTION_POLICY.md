<!-- docs/RETENTION_POLICY.md -->

# Retention и Cleanup Policy

Документ является обязательным архитектурным контрактом. Временные файлы,
vector collections, processing artifacts и logs не могут храниться бессрочно
только потому, что happy-path завершился без явной команды удаления.

## 1. Основные принципы

Каждый storage object относится к одному из классов:

```text
persistent
retained
transient
cache
log
```

Для `transient`, `cache` и `log` MUST существовать конечная retention policy.

Для временного business object MUST храниться или однозначно вычисляться:

```text
owner/service
object type
created_at
last_used_at, если применимо
terminal_at, если применимо
expires_at
cleanup status
storage/vector identifiers
```

Удаление должно быть:

```text
idempotent
retryable
observable
bounded
```

## 2. Default TTL

Foundation baseline:

```text
TEMPORARY_CONTEXT_GRACE_HOURS = 24
STALE_UPLOAD_TTL_HOURS        = 24
PROCESSING_ARTIFACT_TTL_HOURS = 24
LOG_RETENTION_DAYS            = 14
RESULT_RETENTION_DAYS         = 30
```

Это default policy. На infrastructure/application stages значения будут
выведены в `.env.example` как non-secret configuration и смогут переопределяться
без изменения business logic.

## 3. Technical Assignment

Technical Assignment является временным analysis context.

Удаляются:

```text
original T file
Word/PDF preview, если создавался
extracted page text
rendered page images
chunk/page metadata, не нужная после cleanup
T vector collection
intermediate indexing files
```

Default expiration:

```text
analysis reaches terminal state
        + 24 hours grace
        ↓
cleanup eligible
```

Terminal states включают минимум:

```text
completed
failed
canceled
```

Незавершённый/брошенный upload без активного analysis context удаляется через
24 часа после последней подтверждённой активности.

## 4. Technical Assignment vector collection

T vectors не становятся persistent catalog.

Целевой naming pattern:

```text
plan_validator_t_<context_id>
```

Collection registry хранит owner/context/expiration metadata в PostgreSQL.
Нельзя определять срок жизни только разбором имени collection.

Collection удаляется вместе с T context. Если Qdrant временно недоступен,
metadata не помечается окончательно удалённой: cleanup переходит в retryable
failure state.

## 5. Пояснительная записка

ПЗ используется только как временный Project Context.

Временными считаются:

```text
выбранный пользователем page range
extracted text fragments
rendered images выбранных страниц, если нужны pipeline
temporary chunks
PZ vector collection
processing workspace
```

Полный исходный project file не дублируется ради ПЗ без необходимости. Если для
ПЗ создаётся физическая копия выбранного диапазона, эта копия transient.

Default expiration:

```text
analysis terminal state + 24 hours
```

## 6. ПЗ vector collection

Naming pattern:

```text
plan_validator_pz_<context_id>
```

Она никогда не становится `N`, `T`, `U` или `E` collection и не участвует в
blue/green migration persistent knowledge после истечения context.

## 7. Processing artifacts

К transient processing artifacts относятся:

```text
temporary PDF splits
page renders, не входящие в retained result
OCR scratch files
DWG/DXF conversion scratch files
temporary archives
staging directories
partial downloads
failed upload fragments
intermediate JSON
```

Default TTL:

```text
24 hours
```

Successful pipeline SHOULD удалять disposable scratch files сразу после
последнего use. TTL является safety net для crash/restart scenarios, а не
причиной держать уже ненужный файл ещё сутки.

## 8. Main analysis files и results

Основной project document и финальный result не относятся автоматически к T/PZ
transient context.

Foundation default для history-enabled analysis:

```text
main analysis source: 30 days
final result artifacts: 30 days
```

При ручном удалении analysis пользователем cleanup запускается раньше.

Если позже вводится режим «сохранить в истории», retention semantics должны быть
явно зафиксированы отдельным product decision; бесконечное хранение не становится
default случайно.

## 9. Persistent managed knowledge

Не удаляются по transient TTL:

```text
N normative catalog documents
U user package documents
E experience cases
их persistent metadata/vector representations
```

Они хранятся до явного удаления пользователем/администратором либо до другой
отдельно утверждённой business retention policy.

Blue/green obsolete physical collections после успешного alias cutover являются
cleanup candidates и не должны копиться бессрочно.

## 10. Logs

Logs имеют две bounded защиты.

### Docker stdout/stderr

Для application containers используется Docker logging driver с конечной
rotation policy. Foundation target:

```text
max-size = 10 MiB
max-file = 5
```

### Project log files

По требованию проекта каждый service MAY дополнительно писать structured log в
собственный каталог:

```text
var/log/<service>/
```

Нельзя нескольким processes писать в один общий `app.log` без безопасного
multi-process handler.

Target policy:

```text
single active file soft limit: 20 MiB
rotated archives per service: 7
absolute age cleanup: 14 days
```

Size rotation защищает от всплеска traffic, age cleanup — от редко меняющихся,
но старых файлов.

Secrets, tokens, passwords, Authorization headers и полные пользовательские
документы в logs запрещены независимо от retention.

## 11. Cleanup lifecycle

Рекомендуемые состояния transient object:

```text
active
expired
cleanup_pending
cleaning
cleanup_failed
cleaned
```

Допустима более компактная реализация, если сохраняются те же инварианты.

Критический инвариант:

> SQL/registry state не должен утверждать, что object полностью удалён, пока
> принадлежащие ему обязательные filesystem/vector resources не очищены либо
> явно не подтверждено, что они уже отсутствуют.

`not found` при повторном delete считается успешным идемпотентным состоянием.

## 12. Ownership cleanup

Каждый bounded context удаляет данные, которыми владеет.

Пример:

```text
context-service
    -> T files
    -> T renders/text
    -> T collection
    -> PZ temporary files
    -> PZ collection

document-service
    -> document processing scratch
    -> expired main analysis artifacts

result-service
    -> expired result artifacts
```

Не создаётся shell-script, который вслепую рекурсивно удаляет чужие service
volumes по возрасту файла.

## 13. Scheduling

Cleanup не является GPU-heavy operation и не должен попадать в GPU queue.

Планируемая схема:

```text
shared n8n scheduled workflow
        ↓
service-owned internal cleanup endpoints/use-cases
        ↓
small bounded batches
```

Допустим startup recovery scan, но normal service startup не должен блокироваться
на полном обходе всех старых данных.

## 14. Batch и limits

Cleanup выполняется ограниченными batch, чтобы housekeeping не превращался в
длительную блокирующую операцию.

Будущая configuration должна включать минимум:

```text
cleanup interval
cleanup batch size
cleanup retry delay/max attempts or retry policy
TTL values
log retention values
```

## 15. Observability cleanup

Не логировать каждый успешно удалённый chunk/file на INFO.

Один cleanup batch пишет summary:

```text
event=cleanup_completed
service=<service>
scanned_count=<n>
cleaned_count=<n>
failed_count=<n>
duration_ms=<n>
```

Ошибка конкретного business object должна содержать object ID/context ID, но не
секреты и не полный текст документа.

Metrics/diagnostics должны позволять увидеть:

```text
expired objects awaiting cleanup
cleanup failures
oldest expired object age
temporary bytes if measurable
number of temporary Qdrant collections
```

## 16. Crash recovery

После crash возможны orphan candidates:

```text
filesystem object есть, SQL transaction не завершилась
collection создана, indexing не завершился
status остался cleaning
partial conversion file остался в staging
```

Cleanup/recovery implementation MUST учитывать такие состояния.

Для resources, которые невозможно безопасно связать с owner metadata,
автоматическое удаление запрещено. Сначала объект попадает в diagnostic orphan
report.

## 17. Manual delete

Явное удаление пользователем имеет приоритет над TTL:

```text
user deletes context/analysis
        ↓
mark deletion requested
        ↓
service-owned cleanup
        ↓
verify owned resources absent
        ↓
final deleted state
```

HTTP request не обязан ждать удаления большого vector/file set. Если операция
длительная, API возвращает deletion lifecycle state, но cleanup должен быть
надёжно продолжен.

## 18. Tests обязательны

Для каждого cleanup use-case нужны минимум:

```text
happy-path deletion
already-missing resource/idempotency
filesystem failure
Qdrant failure
retry after cleanup_failed
TTL boundary
manual delete before TTL
stale upload cleanup
persistent N/U/E not selected by transient cleanup
```

Runtime tests дополнительно проверят, что temporary files/collections реально
исчезают после configurable short TTL в test environment.
