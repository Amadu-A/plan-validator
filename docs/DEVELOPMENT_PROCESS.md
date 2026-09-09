<!-- docs/DEVELOPMENT_PROCESS.md -->

# Процесс разработки Plan Validator

Документ фиксирует подтверждённый пошаговый workflow разработки и обязателен для
LLM/developer работы над repository.

## 1. Один этап — одно сообщение с кодом

Каждый roadmap stage реализуется одним законченным набором изменений.

Запрещено без отдельного согласования превращать этап в:

```text
8.1
8.2
8.3
```

Если после проверки найдена ошибка, она исправляется в рамках того же этапа.
Следующий этап начинается только после зелёной проверки текущего.

## 2. Полные файлы

При создании или изменении файла показывается его полный актуальный content.
Diff-only ответы не используются как основной способ передачи кода.

Для каждого файла обязательно указывается относительный путь от корня проекта.
Если синтаксис допускает comment, путь также указывается вверху файла в
соответствии с shared engineering standard.

Перед каждым файлом LLM явно пишет:

```text
НОВЫЙ ФАЙЛ
```

или:

```text
ИЗМЕНЯЕМ ФАЙЛ
```

Перед перечнем файлов этапа сначала даётся Linux-команда, которая создаёт все
новые каталоги и пустые файлы текущего этапа. Если новых файлов нет, это
указывается явно.

Markdown-файлы передаются пользователю как downloadable attachments/links.
Целевой README после всех 22 этапов передаётся один раз отдельным downloadable
файлом и не дублируется целиком в каждом последующем этапе.

## 3. Цикл этапа

```text
1. Зафиксировать цель этапа.
2. Дать Linux-команду создания новых directories/files.
3. Показать полный content всех создаваемых/изменяемых non-Markdown files.
4. Приложить создаваемые/изменяемые Markdown files для скачивания.
5. Дать validation commands.
6. Пользователь применяет изменения.
7. Запускаются lint/unit/integration/runtime tests, относящиеся к этапу.
8. Пользователь делает commit/push.
9. LLM проверяет GitHub repository.
10. Ошибки исправляются без перехода к следующему stage.
11. После green state начинается следующий stage.
```

## 4. Нельзя опережать этапы

Foundation stage не должен создавать половину Analysis Service «на будущее».
Infrastructure stage не должен внедрять business retrieval logic.

Новый файл появляется тогда, когда его ответственность действительно нужна
текущему этапу.

Это снижает количество пустых abstractions и speculative architecture.

## 5. Reference project

`Amadu-A/PDRD-validation` разрешено использовать для:

```text
functional requirements
N/T/U/E semantics
workflow ideas
visual frontend direction
examples of user flows
```

Запрещено считать его legacy implementation source of truth.

Если reference code противоречит pinned shared engineering standard, выбирается
новый standard/project architecture.

## 6. Документирование

Каждый source/config/script/template file имеет русское описание назначения,
responsibility, integrations и важных side effects.

Каждая функция, метод и класс документируется содержательно на русском языке.

Комментарий не должен механически пересказывать строку кода.

## 7. Размер и ответственность файлов

Жёсткий лимит строк не вводится, но один файл не должен быть контейнером для
несвязанных operations.

Причины декомпозиции:

```text
несколько разных ресурсов в router
несколько aggregates в repository file
I/O + business rules + HTTP mapping в одной функции
много независимых try/except веток
невозможно назвать функцию одним действием
тест требует множество несвязанных fixtures
```

## 8. Quality gate

Каждый этап должен иметь проверяемый gate.

Базовый Python gate:

```text
Ruff lint
Ruff format check
Pytest
architecture tests
git diff --check
```

По мере появления infrastructure добавляются:

```text
docker compose config
unit tests
integration tests
migration tests
API tests
runtime tests
GPU tests
queue tests
frontend tests/E2E
```

## 9. Измерение производительности

Нельзя отправлять operation в background queue только по предположению, что она
«наверное тяжёлая».

Для значимых operations используется timing decorator. После измерений operation
классифицируется как:

```text
inline lightweight
background CPU-heavy
background GPU-heavy
```

GPU competition сама по себе является достаточной причиной serialization.

## 10. Временные данные

Любая feature, создающая temporary file/vector collection/cache, в том же этапе
обязана определить:

```text
owner
TTL/expires_at
cleanup use-case
failure/retry behavior
tests cleanup
```

Feature не считается законченной, если умеет создавать временный resource, но
не умеет гарантированно его удалить.

Полный контракт находится в `docs/RETENTION_POLICY.md`.

## 11. Git commits

Commit должен соответствовать одному логическому stage/fix.

Foundation recommendation:

```text
feat: initialize plan-validator foundation
```

Исправление текущего этапа:

```text
fix: correct foundation validation
```

Не смешивать unrelated local files и runtime data.
