# tests/runtime/context_service/test_context_runtime.py

"""Linux E2E temporary Context, real Qwen retrieval and SIGKILL recovery."""

import hashlib
import json
import os
import subprocess
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from qdrant_client import QdrantClient

_RUN_RUNTIME = os.environ.get("PLAN_VALIDATOR_RUN_CONTEXT_RUNTIME_E2E") == "1"

_POLL_INTERVAL_SECONDS = 0.25
_RUNNING_TIMEOUT_SECONDS = 120.0
_INDEX_TIMEOUT_SECONDS = 600.0
_QUEUE_DRAIN_TIMEOUT_SECONDS = 180.0
_CLEANUP_TIMEOUT_SECONDS = 120.0
_INTERNAL_SEARCH_TIMEOUT_SECONDS = 520.0


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    """Минимальное DB-состояние recoverable Context indexing job."""

    state: str
    attempt: int
    max_attempts: int
    lease_owner: str | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class QueueSnapshot:
    """RabbitMQ queue counters для bounded recovery assertions."""

    ready: int
    unacked: int
    consumers: int


def _database_connection() -> psycopg.Connection[tuple[object, ...]]:
    """Открывает host connection к project PostgreSQL."""
    return psycopg.connect(
        host="127.0.0.1",
        port=int(
            os.environ.get(
                "PLAN_VALIDATOR_POSTGRES_HOST_PORT",
                "5438",
            )
        ),
        dbname=os.environ.get(
            "PLAN_VALIDATOR_POSTGRES_DB",
            "plan_validator",
        ),
        user=os.environ.get(
            "PLAN_VALIDATOR_POSTGRES_USER",
            "plan_validator",
        ),
        password=os.environ["PLAN_VALIDATOR_POSTGRES_PASSWORD"],
    )


def _lookup_user_id(
    email: str,
) -> UUID:
    """Возвращает UUID runtime user из реальной Auth schema."""
    with (
        _database_connection() as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            SELECT id
            FROM auth.users
            WHERE email = %s
            """,
            (email.casefold(),),
        )

        row = cursor.fetchone()

    assert row is not None

    return UUID(str(row[0]))


def _job_snapshot(
    job_id: UUID,
) -> JobSnapshot | None:
    """Читает state/attempt/lease/error durable Context job."""
    with (
        _database_connection() as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            SELECT
                state,
                attempt,
                max_attempts,
                lease_owner,
                last_error
            FROM context.index_jobs
            WHERE id = %s
            """,
            (job_id,),
        )

        row = cursor.fetchone()

    if row is None:
        return None

    return JobSnapshot(
        state=str(row[0]),
        attempt=int(row[1]),
        max_attempts=int(row[2]),
        lease_owner=(None if row[3] is None else str(row[3])),
        last_error=(None if row[4] is None else str(row[4])),
    )


def _source_snapshot(
    source_id: UUID,
) -> (
    tuple[
        str,
        str | None,
        int,
    ]
    | None
):
    """Читает source state/fingerprint/chunk_count из Context registry."""
    with (
        _database_connection() as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            SELECT
                state,
                active_fingerprint,
                chunk_count
            FROM context.sources
            WHERE id = %s
            """,
            (source_id,),
        )

        row = cursor.fetchone()

    if row is None:
        return None

    return (
        str(row[0]),
        (None if row[1] is None else str(row[1])),
        int(row[2]),
    )


def _context_state(
    context_id: UUID,
) -> str | None:
    """Возвращает persistent lifecycle state одного Project Context."""
    with (
        _database_connection() as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            SELECT state
            FROM context.project_contexts
            WHERE id = %s
            """,
            (context_id,),
        )

        row = cursor.fetchone()

    return None if row is None else str(row[0])


def _context_payload_rows(
    context_id: UUID,
) -> tuple[int, int]:
    """Считает temporary source/job rows после physical cleanup."""
    with (
        _database_connection() as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            SELECT count(*)
            FROM context.sources
            WHERE context_id = %s
            """,
            (context_id,),
        )

        source_row = cursor.fetchone()

        assert source_row is not None

        source_count = int(source_row[0])

        cursor.execute(
            """
            SELECT count(*)
            FROM context.index_jobs
            WHERE context_id = %s
            """,
            (context_id,),
        )

        job_row = cursor.fetchone()

        assert job_row is not None

        job_count = int(job_row[0])

    return (
        source_count,
        job_count,
    )


def _wait_until(
    predicate: Callable[[], bool],
    *,
    timeout_seconds: float,
    description: str,
) -> None:
    """Bounded polling helper eventual-consistency assertions."""
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        if predicate():
            return

        time.sleep(_POLL_INTERVAL_SECONDS)

    raise AssertionError(f"Timed out waiting for {description}")


def _wait_for_job_success(
    job_id: UUID,
    *,
    minimum_attempt: int,
    timeout_seconds: float = (_INDEX_TIMEOUT_SECONDS),
) -> JobSnapshot:
    """Ждёт success, но падает сразу при terminal failure/cancel."""
    deadline = time.monotonic() + timeout_seconds

    last_snapshot: JobSnapshot | None = None

    while time.monotonic() < deadline:
        last_snapshot = _job_snapshot(job_id)

        if last_snapshot is None:
            time.sleep(_POLL_INTERVAL_SECONDS)

            continue

        if last_snapshot.state == "succeeded":
            assert last_snapshot.attempt >= minimum_attempt

            return last_snapshot

        if last_snapshot.state in {
            "failed",
            "canceled",
        }:
            raise AssertionError(
                "Context job became terminal before success: "
                f"state={last_snapshot.state} "
                f"attempt={last_snapshot.attempt} "
                f"error={last_snapshot.last_error!r}"
            )

        time.sleep(_POLL_INTERVAL_SECONDS)

    raise AssertionError(
        f"Timed out waiting for Context job success; last_snapshot={last_snapshot!r}"
    )


def _context_request(
    method: str,
    path: str,
    body: dict[
        str,
        object,
    ]
    | None = None,
    *,
    timeout_seconds: float = 30.0,
) -> tuple[
    int,
    dict[
        str,
        object,
    ],
]:
    """Вызывает internal Context endpoint внутри Context container namespace."""
    script = r"""
import json
import sys
import urllib.error
import urllib.request

method = sys.argv[1]
path = sys.argv[2]
timeout = float(sys.argv[3])

raw = sys.stdin.read()

data = (
    raw.encode("utf-8")
    if raw
    else None
)

request = urllib.request.Request(
    "http://127.0.0.1:8000" + path,
    data=data,
    method=method,
    headers={
        "Content-Type": "application/json",
        "X-Correlation-ID": "context-runtime-e2e",
    },
)

try:
    with urllib.request.urlopen(
        request,
        timeout=timeout,
    ) as response:
        status = response.status
        payload = response.read().decode("utf-8")

except urllib.error.HTTPError as error:
    status = error.code
    payload = error.read().decode("utf-8")

print(
    json.dumps(
        {
            "status": status,
            "payload": payload,
        }
    )
)
"""

    completed = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "context-service",
            "python",
            "-c",
            script,
            method,
            path,
            str(timeout_seconds),
        ],
        input=(
            ""
            if body is None
            else json.dumps(
                body,
                ensure_ascii=False,
            )
        ),
        text=True,
        capture_output=True,
        check=True,
        timeout=(timeout_seconds + 30.0),
    )

    envelope = json.loads(completed.stdout.strip())

    payload_text = str(envelope["payload"])

    payload = json.loads(payload_text) if payload_text else {}

    return (
        int(envelope["status"]),
        payload,
    )


def _container_id(
    service: str,
) -> str:
    """Возвращает Compose container id обязательного runtime service."""
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "ps",
            "-q",
            service,
        ],
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )

    container_id = completed.stdout.strip()

    assert container_id, f"Compose service has no container: {service}"

    return container_id


def _container_is_healthy(
    service: str,
) -> bool:
    """Проверяет running/healthy состояние Compose service."""
    with suppress(Exception):
        container_id = _container_id(service)

        completed = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                (
                    "{{.State.Status}}|"
                    "{{if .State.Health}}"
                    "{{.State.Health.Status}}"
                    "{{else}}none{{end}}"
                ),
                container_id,
            ],
            text=True,
            capture_output=True,
            check=True,
            timeout=30,
        )

        status, health = completed.stdout.strip().split(
            "|",
            maxsplit=1,
        )

        return status == "running" and health in {
            "healthy",
            "none",
        }

    return False


def _kill_and_restart_context_worker() -> None:
    """SIGKILL'ит только Context worker и возвращает его в healthy runtime."""
    subprocess.run(
        [
            "docker",
            "compose",
            "kill",
            "-s",
            "KILL",
            "context-worker",
        ],
        check=True,
        timeout=30,
    )

    subprocess.run(
        [
            "docker",
            "compose",
            "up",
            "-d",
            "context-worker",
        ],
        check=True,
        timeout=120,
    )

    _wait_until(
        lambda: _container_is_healthy("context-worker"),
        timeout_seconds=120.0,
        description=("restarted Context worker health"),
    )


def _rabbitmq_container_id() -> str:
    """Находит единственный shared RabbitMQ container по compose label/network."""
    completed = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            "network=ai-shared",
            "--filter",
            ("label=com.docker.compose.service=rabbitmq"),
            "--format",
            "{{.ID}}",
        ],
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )

    ids = [line.strip() for line in completed.stdout.splitlines() if line.strip()]

    assert len(ids) == 1, f"Expected one shared RabbitMQ container, got {ids}"

    return ids[0]


def _rabbit_queue_snapshot(
    queue_name: str,
) -> QueueSnapshot:
    """Читает Ready/Unacked/Consumers из project RabbitMQ vhost."""
    completed = subprocess.run(
        [
            "docker",
            "exec",
            _rabbitmq_container_id(),
            "rabbitmqctl",
            "list_queues",
            "-p",
            "/plan-validator",
            "name",
            "messages_ready",
            "messages_unacknowledged",
            "consumers",
            "--silent",
        ],
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )

    for line in completed.stdout.splitlines():
        fields = line.split()

        if len(fields) == 4 and fields[0] == queue_name:
            return QueueSnapshot(
                ready=int(fields[1]),
                unacked=int(fields[2]),
                consumers=int(fields[3]),
            )

    raise AssertionError(f"RabbitMQ queue was not found: {queue_name}")


def _qdrant_client() -> QdrantClient:
    """Создаёт host Qdrant client для temporary collection assertions."""
    return QdrantClient(
        host="127.0.0.1",
        port=int(
            os.environ.get(
                "PLAN_VALIDATOR_QDRANT_HTTP_HOST_PORT",
                "6335",
            )
        ),
        prefer_grpc=False,
        timeout=30,
    )


def _collection_name(
    context_id: UUID,
    kind: str,
) -> str:
    """Повторяет public deterministic Stage 10 collection naming contract."""
    return f"plan_validator_{kind.casefold()}_{context_id.hex}"


def _collection_exists(
    context_id: UUID,
    kind: str,
) -> bool:
    """Проверяет наличие typed Context collection."""
    client = _qdrant_client()

    try:
        return bool(
            client.collection_exists(
                _collection_name(
                    context_id,
                    kind,
                )
            )
        )

    finally:
        client.close()


def _collection_vector_size(
    context_id: UUID,
    kind: str,
) -> int:
    """Возвращает vector dimension typed Context collection."""
    client = _qdrant_client()

    try:
        info = client.get_collection(
            _collection_name(
                context_id,
                kind,
            )
        )

        vectors = info.config.params.vectors

        size = getattr(
            vectors,
            "size",
            None,
        )

        assert size is not None

        return int(size)

    finally:
        client.close()


def _cleanup_qdrant_context(
    context_id: UUID,
) -> None:
    """Best-effort удаляет обе runtime collections после failed test."""
    client = _qdrant_client()

    try:
        for kind in (
            "t",
            "pz",
        ):
            name = _collection_name(
                context_id,
                kind,
            )

            with suppress(Exception):
                if client.collection_exists(name):
                    client.delete_collection(name)

    finally:
        client.close()


def _cleanup_database(
    emails: list[str],
    context_ids: list[UUID],
) -> None:
    """Best-effort удаляет runtime Context/Auth rows после assertions."""
    with (
        _database_connection() as connection,
        connection.cursor() as cursor,
    ):
        for context_id in context_ids:
            cursor.execute(
                """
                DELETE FROM context.index_jobs
                WHERE context_id = %s
                """,
                (context_id,),
            )

            cursor.execute(
                """
                DELETE FROM context.sources
                WHERE context_id = %s
                """,
                (context_id,),
            )

            cursor.execute(
                """
                DELETE FROM context.project_contexts
                WHERE id = %s
                """,
                (context_id,),
            )

        for email in emails:
            cursor.execute(
                """
                DELETE FROM auth.users
                WHERE email = %s
                """,
                (email.casefold(),),
            )


def _create_authenticated_client(
    email: str,
    password: str,
) -> tuple[
    httpx.Client,
    UUID,
]:
    """Регистрирует disposable runtime user и cookie-aware Gateway client."""
    gateway_port = int(
        os.environ.get(
            "PLAN_VALIDATOR_GATEWAY_HOST_PORT",
            "8000",
        )
    )

    client = httpx.Client(
        base_url=(f"http://127.0.0.1:{gateway_port}"),
        timeout=30,
    )

    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
        },
    )

    assert registered.status_code == 201, registered.text

    return (
        client,
        _lookup_user_id(email),
    )


def _create_context(
    client: httpx.Client,
) -> UUID:
    """Создаёт Project Context через public authenticated Gateway facade."""
    response = client.post("/api/v1/project-contexts")

    assert response.status_code == 201, response.text

    payload = response.json()

    assert "user_id" not in payload

    return UUID(payload["id"])


def _register_source(
    client: httpx.Client,
    *,
    context_id: UUID,
    kind: str,
    original_name: str,
    source_text: str,
) -> UUID:
    """Регистрирует T/PZ metadata через public Gateway facade."""
    source_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()

    response = client.post(
        (f"/api/v1/project-contexts/{context_id}/sources"),
        json={
            "kind": kind,
            "original_name": original_name,
            "source_sha256": source_sha256,
        },
    )

    assert response.status_code == 201, response.text

    payload = response.json()

    assert "user_id" not in payload

    assert payload["kind"] == kind

    return UUID(payload["id"])


def _enqueue_index(
    *,
    user_id: UUID,
    context_id: UUID,
    source_id: UUID,
    chunks: list[
        dict[
            str,
            object,
        ]
    ],
) -> UUID:
    """Имитирует будущий trusted Document Service normalized-chunk handoff."""
    status, payload = _context_request(
        "POST",
        (f"/internal/v1/context/contexts/{context_id}/sources/{source_id}/index"),
        {
            "user_id": str(user_id),
            "chunks": chunks,
        },
    )

    assert status == 202, payload

    assert payload["status"] == "queued"

    job_id = payload.get("job_id")

    assert job_id is not None

    return UUID(str(job_id))


def _search(
    *,
    user_id: UUID,
    context_id: UUID,
    kind: str,
    text: str,
) -> list[
    dict[
        str,
        object,
    ]
]:
    """Выполняет real Qwen query embedding и typed Context search."""
    status, payload = _context_request(
        "POST",
        (f"/internal/v1/context/contexts/{context_id}/search/{kind}"),
        {
            "user_id": str(user_id),
            "text": text,
            "limit": 5,
            "score_threshold": -1.0,
        },
        timeout_seconds=(_INTERNAL_SEARCH_TIMEOUT_SECONDS),
    )

    assert status == 200, payload

    hits = payload.get("hits")

    assert isinstance(
        hits,
        list,
    )

    return hits


def _request_cleanup(
    client: httpx.Client,
    context_id: UUID,
) -> None:
    """Запускает logical-first cleanup через public Gateway facade."""
    response = client.delete(f"/api/v1/project-contexts/{context_id}")

    assert response.status_code == 202, response.text

    assert response.json()["state"] == "cleanup_pending"


@pytest.mark.skipif(
    not _RUN_RUNTIME,
    reason=("Set PLAN_VALIDATOR_RUN_CONTEXT_RUNTIME_E2E=1 for Linux Stage 10 E2E"),
)
def test_context_runtime_qwen_sigkill_recovery_and_next_user() -> None:
    """Доказывает T/PZ retrieval и recovery без purge/manual cancellation."""
    first_email = f"context-runtime-a-{uuid4().hex}@example.com"

    second_email = f"context-runtime-b-{uuid4().hex}@example.com"

    password = "runtime-context-password-123"

    emails = [
        first_email,
        second_email,
    ]

    context_ids: list[UUID] = []

    clients: list[httpx.Client] = []

    try:
        (
            first_client,
            first_user_id,
        ) = _create_authenticated_client(
            first_email,
            password,
        )

        clients.append(first_client)

        first_context_id = _create_context(first_client)

        context_ids.append(first_context_id)

        technical_text = (
            "Техническое задание требует предусмотреть "
            "резервирование кабельных линий и отдельную "
            "маркировку оборудования заказчика."
        )

        technical_source_id = _register_source(
            first_client,
            context_id=first_context_id,
            kind="T",
            original_name=("stage10-technical-assignment.pdf"),
            source_text=technical_text,
        )

        first_job_id = _enqueue_index(
            user_id=first_user_id,
            context_id=first_context_id,
            source_id=technical_source_id,
            chunks=[
                {
                    "chunk_id": "t-p1-0",
                    "text": technical_text,
                    "page_number": 1,
                    "fragment_index": 0,
                    "heading": ("Требования заказчика"),
                },
                {
                    "chunk_id": "t-p2-0",
                    "text": (
                        "В техническом задании указано "
                        "обеспечить раздельный учёт основных "
                        "и резервных проектных решений."
                    ),
                    "page_number": 2,
                    "fragment_index": 0,
                    "heading": ("Резервирование"),
                },
            ],
        )

        _wait_until(
            lambda: (
                (snapshot := _job_snapshot(first_job_id)) is not None
                and snapshot.state == "running"
                and snapshot.attempt == 1
                and snapshot.lease_owner is not None
            ),
            timeout_seconds=(_RUNNING_TIMEOUT_SECONDS),
            description=("first Context job RUNNING attempt=1"),
        )

        embedding_container_before = _container_id("embedding-worker")

        running_before_kill = _job_snapshot(first_job_id)

        assert running_before_kill is not None

        print(
            "first job before SIGKILL:",
            first_job_id,
            running_before_kill,
            flush=True,
        )

        _kill_and_restart_context_worker()

        recovered = _wait_for_job_success(
            first_job_id,
            minimum_attempt=2,
        )

        print(
            "first job after recovery:",
            first_job_id,
            recovered,
            flush=True,
        )

        assert _container_id("embedding-worker") == embedding_container_before

        assert _container_is_healthy("embedding-worker")

        technical_source = _source_snapshot(technical_source_id)

        assert technical_source is not None

        assert technical_source[0] == "indexed"

        assert technical_source[1] is not None

        assert technical_source[2] == 2

        assert _collection_exists(
            first_context_id,
            "t",
        )

        assert (
            _collection_vector_size(
                first_context_id,
                "t",
            )
            == 4096
        )

        technical_hits = _search(
            user_id=first_user_id,
            context_id=first_context_id,
            kind="T",
            text=("Какие требования заказчика есть к резервным кабельным линиям?"),
        )

        assert technical_hits

        assert all(hit["kind"] == "T" for hit in technical_hits)

        assert all(
            hit["semantic_role"] == ("project_context_non_normative") for hit in technical_hits
        )

        assert all(hit["source_id"] == str(technical_source_id) for hit in technical_hits)

        (
            second_client,
            second_user_id,
        ) = _create_authenticated_client(
            second_email,
            password,
        )

        clients.append(second_client)

        second_context_id = _create_context(second_client)

        context_ids.append(second_context_id)

        second_text = (
            "Второй пользователь требует предусмотреть "
            "автоматический контроль состояния "
            "инженерного оборудования."
        )

        second_source_id = _register_source(
            second_client,
            context_id=second_context_id,
            kind="T",
            original_name=("stage10-second-user-tz.pdf"),
            source_text=second_text,
        )

        second_job_id = _enqueue_index(
            user_id=second_user_id,
            context_id=second_context_id,
            source_id=second_source_id,
            chunks=[
                {
                    "chunk_id": ("second-t-p1-0"),
                    "text": second_text,
                    "page_number": 1,
                    "fragment_index": 0,
                }
            ],
        )

        second_success = _wait_for_job_success(
            second_job_id,
            minimum_attempt=1,
        )

        print(
            "second user job:",
            second_job_id,
            second_success,
            flush=True,
        )

        second_source = _source_snapshot(second_source_id)

        assert second_source is not None

        assert second_source[0] == "indexed"

        project_note_text = (
            "Пояснительная записка описывает размещение "
            "щитов в технических помещениях и маршруты "
            "резервных кабельных трасс."
        )

        project_note_source_id = _register_source(
            first_client,
            context_id=(first_context_id),
            kind="PZ",
            original_name=("stage10-project-note.pdf"),
            source_text=(project_note_text),
        )

        project_note_job_id = _enqueue_index(
            user_id=first_user_id,
            context_id=(first_context_id),
            source_id=(project_note_source_id),
            chunks=[
                {
                    "chunk_id": "pz-p1-0",
                    "text": (project_note_text),
                    "page_number": 1,
                    "fragment_index": 0,
                    "heading": ("Проектные решения"),
                }
            ],
        )

        _wait_for_job_success(
            project_note_job_id,
            minimum_attempt=1,
        )

        assert _collection_exists(
            first_context_id,
            "pz",
        )

        assert (
            _collection_vector_size(
                first_context_id,
                "pz",
            )
            == 4096
        )

        project_note_hits = _search(
            user_id=first_user_id,
            context_id=first_context_id,
            kind="PZ",
            text=("Где размещены щиты и как проходят резервные трассы?"),
        )

        assert project_note_hits

        assert all(hit["kind"] == "PZ" for hit in project_note_hits)

        assert all(
            hit["semantic_role"] == ("project_context_non_normative") for hit in project_note_hits
        )

        assert all(hit["source_id"] == str(project_note_source_id) for hit in project_note_hits)

        assert all(hit["source_id"] != str(technical_source_id) for hit in project_note_hits)

        _wait_until(
            lambda: (
                (context_queue := _rabbit_queue_snapshot("plan-validator.context.index")).ready == 0
                and context_queue.unacked == 0
                and context_queue.consumers >= 1
                and (
                    embedding_queue := _rabbit_queue_snapshot("plan-validator.gpu.embedding")
                ).ready
                == 0
                and embedding_queue.unacked == 0
                and embedding_queue.consumers >= 1
            ),
            timeout_seconds=(_QUEUE_DRAIN_TIMEOUT_SECONDS),
            description=("Context/Embedding queues Ready=0 Unacked=0"),
        )

        print(
            "context queue:",
            _rabbit_queue_snapshot("plan-validator.context.index"),
            flush=True,
        )

        print(
            "embedding queue:",
            _rabbit_queue_snapshot("plan-validator.gpu.embedding"),
            flush=True,
        )

        _request_cleanup(
            first_client,
            first_context_id,
        )

        _request_cleanup(
            second_client,
            second_context_id,
        )

        for context_id in (
            first_context_id,
            second_context_id,
        ):
            _wait_until(
                lambda context_id=context_id: (
                    _context_state(context_id) == "cleaned"
                    and _context_payload_rows(context_id)
                    == (
                        0,
                        0,
                    )
                    and not _collection_exists(
                        context_id,
                        "t",
                    )
                    and not _collection_exists(
                        context_id,
                        "pz",
                    )
                ),
                timeout_seconds=(_CLEANUP_TIMEOUT_SECONDS),
                description=(f"physical cleanup for Context {context_id}"),
            )

    finally:
        with suppress(Exception):
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "up",
                    "-d",
                    "context-worker",
                ],
                check=True,
                timeout=120,
            )

        for client in clients:
            with suppress(Exception):
                client.close()

        for context_id in context_ids:
            with suppress(Exception):
                _cleanup_qdrant_context(context_id)

        with suppress(Exception):
            _cleanup_database(
                emails,
                context_ids,
            )
