# tests/unit/context_service/test_worker_recovery.py

"""Unit tests Rabbit delivery recovery semantics Context worker."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from context_service.application.use_cases.index_jobs import ClaimContextIndexResult
from context_service.core.settings import ContextSettings
from context_service.domain.exceptions import ContextEmbeddingError
from context_service.domain.models import (
    ContextIndexJob,
    ContextIndexJobState,
    ContextSourceKind,
    NormalizedContextChunk,
)
from context_service.infrastructure.messaging.schemas import ContextIndexJobMessage
from context_service.infrastructure.messaging.worker import (
    ContextWorkerRuntime,
    build_message_handler,
)
from pydantic import SecretStr


class FakeMessage:
    """Минимальный aio-pika-like delivery для handler tests."""

    def __init__(self, payload: ContextIndexJobMessage) -> None:
        """Сериализует message body и counters."""
        self.body = payload.model_dump_json().encode("utf-8")
        self.acked = 0
        self.nacked = 0
        self.rejected = 0

    async def ack(self) -> None:
        """Фиксирует ACK."""
        self.acked += 1

    async def nack(self, *, requeue: bool) -> None:
        """Фиксирует NACK."""
        assert requeue is True
        self.nacked += 1

    async def reject(self, *, requeue: bool) -> None:
        """Фиксирует reject."""
        assert requeue is False
        self.rejected += 1


class FakeClaim:
    """Возвращает заранее заданный claim result."""

    def __init__(self, result: ClaimContextIndexResult) -> None:
        """Сохраняет result."""
        self.result = result

    async def execute(self, **_: object) -> ClaimContextIndexResult:
        """Возвращает result."""
        return self.result


class FakeHeartbeat:
    """Heartbeat dependency, которая не должна успеть сработать в unit test."""

    async def execute(self, **_: object) -> ContextIndexJob:
        """Неожиданное выполнение heartbeat считается ошибкой теста."""
        raise AssertionError("heartbeat must not fire in this short test")


class FakeFail:
    """Переводит transient attempt в RETRY_WAIT без Rabbit requeue."""

    def __init__(self, job: ContextIndexJob, now: datetime) -> None:
        """Сохраняет fixture."""
        self.job = job
        self.now = now
        self.calls = 0

    async def execute(self, **_: object) -> ContextIndexJob:
        """Имитирует persisted retry state."""
        self.calls += 1
        return self.job.schedule_retry(
            changed_at=self.now,
            next_attempt_at=self.now + timedelta(seconds=5),
            error_message="temporary embedding failure",
        )


class FakeSuccessfulIndex:
    """Возвращает terminal success."""

    def __init__(self, job: ContextIndexJob, now: datetime) -> None:
        """Сохраняет fixture."""
        self.job = job
        self.now = now
        self.calls = 0

    async def execute(self, **_: object) -> ContextIndexJob:
        """Фиксирует execution."""
        self.calls += 1
        return self.job.succeed(changed_at=self.now)


class FakeTransientIndex:
    """Имитирует transient Embedding dependency failure."""

    def __init__(self) -> None:
        """Инициализирует counter."""
        self.calls = 0

    async def execute(self, **_: object) -> ContextIndexJob:
        """Поднимает recoverable dependency error."""
        self.calls += 1
        raise ContextEmbeddingError("temporary GPU queue failure")


def build_running_job() -> tuple[datetime, ContextIndexJob]:
    """Создаёт claimed RUNNING job."""
    now = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
    job = ContextIndexJob(
        id=uuid4(),
        context_id=uuid4(),
        source_id=uuid4(),
        user_id=uuid4(),
        kind=ContextSourceKind.TECHNICAL_ASSIGNMENT,
        fingerprint="a" * 64,
        correlation_id="corr-worker",
        chunks=(NormalizedContextChunk(chunk_id="c1", text="temporary context"),),
        state=ContextIndexJobState.RUNNING,
        attempt=1,
        max_attempts=3,
        deadline_at=now + timedelta(minutes=12),
        next_attempt_at=None,
        dispatched_at=now,
        lease_owner="worker-test",
        lease_expires_at=now + timedelta(seconds=60),
        last_error=None,
        created_at=now,
        updated_at=now,
    )
    return now, job


def build_settings() -> ContextSettings:
    """Создаёт settings без чтения local .env."""
    return ContextSettings(
        postgres_password=SecretStr("postgres-test"),
        rabbitmq_password=SecretStr("rabbit-test"),
        _env_file=None,
    )


def test_duplicate_delivery_with_live_lease_is_acked_not_requeued() -> None:
    """Повторная доставка не блокирует queue и не запускает второй execution."""
    now, job = build_running_job()
    index = FakeSuccessfulIndex(job, now)
    runtime = ContextWorkerRuntime(
        settings=build_settings(),
        claim=FakeClaim(ClaimContextIndexResult(job=job, claimed=False)),
        heartbeat=FakeHeartbeat(),
        fail=FakeFail(job, now),
        index_source=index,
        worker_id="worker-test",
    )
    payload = ContextIndexJobMessage(
        job_id=job.id,
        correlation_id=job.correlation_id,
    )
    message = FakeMessage(payload)

    asyncio.run(build_message_handler(runtime)(message))

    assert message.acked == 1
    assert message.nacked == 0
    assert message.rejected == 0
    assert index.calls == 0


def test_transient_failure_is_persisted_then_acked_without_poison_loop() -> None:
    """После DB retry_wait текущий Rabbit delivery завершается ACK."""
    now, job = build_running_job()
    failure = FakeFail(job, now)
    index = FakeTransientIndex()
    runtime = ContextWorkerRuntime(
        settings=build_settings(),
        claim=FakeClaim(ClaimContextIndexResult(job=job, claimed=True)),
        heartbeat=FakeHeartbeat(),
        fail=failure,
        index_source=index,
        worker_id="worker-test",
    )
    payload = ContextIndexJobMessage(
        job_id=job.id,
        correlation_id=job.correlation_id,
    )
    message = FakeMessage(payload)

    asyncio.run(build_message_handler(runtime)(message))

    assert index.calls == 1
    assert failure.calls == 1
    assert message.acked == 1
    assert message.nacked == 0
    assert message.rejected == 0
