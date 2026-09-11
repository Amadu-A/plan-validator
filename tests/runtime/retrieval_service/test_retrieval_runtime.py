# tests/runtime/retrieval_service/test_retrieval_runtime.py

"""Runtime E2E Catalog outbox -> Retrieval -> batch Qwen -> Qdrant typed search."""

import json
import os
import subprocess
import time
from collections.abc import Callable
from contextlib import suppress
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
import psycopg
from qdrant_client import QdrantClient, models

_POLL_TIMEOUT_SECONDS = 45.0
_INDEX_TIMEOUT_SECONDS = 1200.0


def _database_connection() -> psycopg.Connection[tuple[object, ...]]:
    """Открывает host connection к project PostgreSQL для E2E assertions/cleanup."""
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


def _lookup_user_id(email: str) -> UUID:
    """Возвращает UUID runtime user из реального Auth schema."""
    with (
        _database_connection() as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT id FROM auth.users WHERE email = %s",
            (email.casefold(),),
        )
        row = cursor.fetchone()

    assert row is not None
    return UUID(str(row[0]))


def _source_state(
    source_id: UUID,
) -> tuple[str, str | None, int] | None:
    """Читает Retrieval registry state/fingerprint/chunk_count напрямую из БД."""
    with (
        _database_connection() as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            SELECT state, active_fingerprint, chunk_count
            FROM retrieval.managed_source_indexes
            WHERE source_id = %s
            """,
            (source_id,),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return (
        str(row[0]),
        None if row[1] is None else str(row[1]),
        int(row[2]),
    )


def _wait_until(
    predicate: Callable[[], bool],
    *,
    timeout_seconds: float,
    description: str,
) -> None:
    """Bounded polling helper runtime eventual-consistency assertions."""
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.5)

    raise AssertionError(f"Timed out waiting for {description}")


def _retrieval_request(
    method: str,
    path: str,
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    """Вызывает internal Retrieval HTTP endpoint внутри container network namespace."""
    script = r"""
import json
import sys
import urllib.error
import urllib.request

method = sys.argv[1]
path = sys.argv[2]
raw = sys.stdin.read()
data = raw.encode("utf-8") if raw else None
request = urllib.request.Request(
    "http://127.0.0.1:8000" + path,
    data=data,
    method=method,
    headers={
        "Content-Type": "application/json",
        "X-Correlation-ID": "retrieval-runtime-e2e",
    },
)

try:
    with urllib.request.urlopen(request, timeout=1810) as response:
        status = response.status
        payload = response.read().decode("utf-8")
except urllib.error.HTTPError as error:
    status = error.code
    payload = error.read().decode("utf-8")

print(json.dumps({"status": status, "payload": payload}))
"""
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "retrieval-service",
            "python",
            "-c",
            script,
            method,
            path,
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
        timeout=1830,
    )
    envelope = json.loads(completed.stdout.strip())
    payload_text = str(envelope["payload"])
    payload = json.loads(payload_text) if payload_text else {}
    return (
        int(envelope["status"]),
        payload,
    )


def _qdrant_source_count(
    source_id: UUID,
) -> int:
    """Считает points source через host-exposed Qdrant HTTP port."""
    client = QdrantClient(
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

    try:
        result = client.count(
            collection_name=("plan_validator_managed_sources"),
            count_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="source_id",
                        match=models.MatchValue(value=str(source_id)),
                    )
                ]
            ),
            exact=True,
        )
        return int(result.count)
    finally:
        client.close()


def _cleanup_qdrant_source(
    source_id: UUID,
) -> None:
    """Best-effort удаляет runtime source points при аварийном завершении test."""
    client = QdrantClient(
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

    try:
        with suppress(Exception):
            client.delete(
                collection_name=("plan_validator_managed_sources"),
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="source_id",
                                match=models.MatchValue(value=str(source_id)),
                            )
                        ]
                    )
                ),
                wait=True,
            )
    finally:
        client.close()


def _cleanup_database(
    email: str,
    source_ids: list[UUID],
) -> None:
    """Удаляет runtime registry/outbox/catalog/auth rows после external cleanup."""
    with (
        _database_connection() as connection,
        connection.cursor() as cursor,
    ):
        for source_id in source_ids:
            cursor.execute(
                """
                DELETE FROM retrieval.managed_source_indexes
                WHERE source_id = %s
                """,
                (source_id,),
            )
            cursor.execute(
                """
                DELETE FROM catalog.source_outbox_messages
                WHERE source_id = %s
                """,
                (source_id,),
            )

        cursor.execute(
            """
            DELETE FROM catalog.managed_sources
            WHERE user_id = (
                SELECT id FROM auth.users WHERE email = %s
            )
            """,
            (email.casefold(),),
        )
        cursor.execute(
            """
            DELETE FROM catalog.sections
            WHERE user_id = (
                SELECT id FROM auth.users WHERE email = %s
            )
            """,
            (email.casefold(),),
        )
        cursor.execute(
            """
            DELETE FROM catalog.system_prompts
            WHERE user_id = (
                SELECT id FROM auth.users WHERE email = %s
            )
            """,
            (email.casefold(),),
        )
        cursor.execute(
            """
            DELETE FROM auth.users
            WHERE email = %s
            """,
            (email.casefold(),),
        )


def test_runtime_n_u_indexing_typed_search_and_delete_cleanup() -> None:
    """Проверяет реальный Stage 9 lifecycle без присвоения parser ownership."""
    email = f"retrieval-runtime-{uuid4().hex}@example.com"
    password = "runtime-retrieval-password-123"
    source_ids: list[UUID] = []

    gateway_port = int(
        os.environ.get(
            "PLAN_VALIDATOR_GATEWAY_HOST_PORT",
            "8000",
        )
    )
    base_url = f"http://127.0.0.1:{gateway_port}"
    pdf = b"%PDF-1.7\nplan-validator-stage-9-synthetic-source\n"

    try:
        with httpx.Client(
            base_url=base_url,
            timeout=20,
        ) as client:
            registered = client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": password,
                },
            )
            assert registered.status_code == 201

            user_id = _lookup_user_id(email)

            section = client.post(
                "/api/v1/catalog/sections",
                json={
                    "title": "Stage 9 Retrieval",
                    "sort_order": 0,
                },
            )
            assert section.status_code == 201

            section_id = UUID(section.json()["id"])

            normative = client.post(
                "/api/v1/catalog/normative-documents",
                params={"section_id": str(section_id)},
                headers={
                    "X-Source-Filename": quote(
                        "СП retrieval runtime.pdf",
                        safe="",
                    ),
                    "Content-Type": ("application/octet-stream"),
                },
                content=pdf,
            )
            assert normative.status_code == 201

            normative_payload = normative.json()
            normative_id = UUID(normative_payload["id"])
            source_ids.append(normative_id)

            user_source = client.post(
                "/api/v1/catalog/user-documents",
                params={"section_id": str(section_id)},
                headers={
                    "X-Source-Filename": quote(
                        "Письмо retrieval runtime.pdf",
                        safe="",
                    ),
                    "Content-Type": ("application/octet-stream"),
                },
                content=pdf,
            )
            assert user_source.status_code == 201

            user_payload = user_source.json()
            user_source_id = UUID(user_payload["id"])
            source_ids.append(user_source_id)

            _wait_until(
                lambda: (
                    _source_state(normative_id) is not None
                    and _source_state(user_source_id) is not None
                ),
                timeout_seconds=(_POLL_TIMEOUT_SECONDS),
                description=("Catalog outbox delivery into Retrieval registry"),
            )

            assert _source_state(normative_id) == (
                "awaiting_chunks",
                None,
                0,
            )

            assert _source_state(user_source_id) == (
                "awaiting_chunks",
                None,
                0,
            )

            index_status, index_response = _retrieval_request(
                "POST",
                (f"/internal/v1/retrieval/sources/{normative_id}/index"),
                {
                    "source_sha256": (normative_payload["sha256"]),
                    "chunks": [
                        {
                            "chunk_id": "p1-0",
                            "text": (
                                "Электрооборудование "
                                "должно быть доступно "
                                "для безопасного "
                                "обслуживания и "
                                "соответствовать "
                                "требованиям проекта."
                            ),
                            "page_number": 1,
                            "fragment_index": 0,
                            "heading": ("Общие требования"),
                        },
                        {
                            "chunk_id": "p1-1",
                            "text": (
                                "Монтаж электрических "
                                "систем следует "
                                "выполнять с учётом "
                                "нормативных требований "
                                "и проектных решений."
                            ),
                            "page_number": 1,
                            "fragment_index": 1,
                            "heading": "Монтаж",
                        },
                    ],
                },
            )

            assert index_status == 202
            assert index_response["status"] == "queued"

            (
                user_index_status,
                user_index_response,
            ) = _retrieval_request(
                "POST",
                (f"/internal/v1/retrieval/sources/{user_source_id}/index"),
                {
                    "source_sha256": (user_payload["sha256"]),
                    "chunks": [
                        {
                            "chunk_id": "p1-0",
                            "text": (
                                "Заказчик требует "
                                "предусмотреть маркировку "
                                "оборудования и отдельный "
                                "перечень эксплуатационных "
                                "обозначений."
                            ),
                            "page_number": 1,
                            "fragment_index": 0,
                            "heading": ("Требования заказчика"),
                        }
                    ],
                },
            )

            assert user_index_status == 202
            assert user_index_response["status"] == "queued"

            _wait_until(
                lambda: (
                    (n_state := _source_state(normative_id)) is not None
                    and n_state[0] == "indexed"
                    and n_state[1] is not None
                    and n_state[2] == 2
                    and (u_state := _source_state(user_source_id)) is not None
                    and u_state[0] == "indexed"
                    and u_state[1] is not None
                    and u_state[2] == 1
                ),
                timeout_seconds=(_INDEX_TIMEOUT_SECONDS * 2),
                description=("real N/U batch Qwen indexing and DB fingerprint activation"),
            )

            assert _qdrant_source_count(normative_id) == 2
            assert _qdrant_source_count(user_source_id) == 1

            (
                search_status,
                search_response,
            ) = _retrieval_request(
                "POST",
                ("/internal/v1/retrieval/normative/search"),
                {
                    "user_id": str(user_id),
                    "text": ("безопасное обслуживание электрооборудования"),
                    "section_ids": [str(section_id)],
                    "limit": 5,
                    "score_threshold": -1.0,
                },
            )

            assert search_status == 200
            assert search_response["hits"]

            hit = search_response["hits"][0]

            assert hit["source_id"] == str(normative_id)
            assert hit["kind"] == "N"
            assert hit["source_content_url"] == (
                f"/api/v1/catalog/normative-documents/{normative_id}/content"
            )

            (
                user_search_status,
                user_search_response,
            ) = _retrieval_request(
                "POST",
                ("/internal/v1/retrieval/user/search"),
                {
                    "user_id": str(user_id),
                    "text": ("маркировка оборудования заказчиком"),
                    "section_ids": [str(section_id)],
                    "limit": 5,
                    "score_threshold": -1.0,
                },
            )

            assert user_search_status == 200
            assert user_search_response["hits"]

            user_hit = user_search_response["hits"][0]

            assert user_hit["source_id"] == str(user_source_id)
            assert user_hit["kind"] == "U"
            assert user_hit["source_content_url"] == (
                f"/api/v1/catalog/user-documents/{user_source_id}/content"
            )

            (
                cross_n_status,
                cross_n_response,
            ) = _retrieval_request(
                "POST",
                ("/internal/v1/retrieval/normative/search"),
                {
                    "user_id": str(user_id),
                    "text": ("маркировка оборудования"),
                    "source_ids": [str(user_source_id)],
                    "score_threshold": -1.0,
                },
            )

            assert cross_n_status == 200
            assert cross_n_response == {"hits": []}

            (
                cross_u_status,
                cross_u_response,
            ) = _retrieval_request(
                "POST",
                ("/internal/v1/retrieval/user/search"),
                {
                    "user_id": str(user_id),
                    "text": ("безопасное обслуживание"),
                    "source_ids": [str(normative_id)],
                    "score_threshold": -1.0,
                },
            )

            assert cross_u_status == 200
            assert cross_u_response == {"hits": []}

            deleted_n = client.delete(f"/api/v1/catalog/normative-documents/{normative_id}")
            deleted_u = client.delete(f"/api/v1/catalog/user-documents/{user_source_id}")

            assert deleted_n.status_code == 204
            assert deleted_u.status_code == 204

            _wait_until(
                lambda: (
                    (n_state := _source_state(normative_id)) is not None
                    and n_state[0] == "deleted"
                    and (u_state := _source_state(user_source_id)) is not None
                    and u_state[0] == "deleted"
                ),
                timeout_seconds=(_POLL_TIMEOUT_SECONDS),
                description=("Retrieval source tombstones after Catalog delete events"),
            )

            _wait_until(
                lambda: (
                    _qdrant_source_count(normative_id) == 0
                    and _qdrant_source_count(user_source_id) == 0
                ),
                timeout_seconds=(_POLL_TIMEOUT_SECONDS),
                description=("Qdrant N/U source cleanup"),
            )

            (
                after_delete_status,
                after_delete_response,
            ) = _retrieval_request(
                "POST",
                ("/internal/v1/retrieval/normative/search"),
                {
                    "user_id": str(user_id),
                    "text": ("безопасное обслуживание"),
                    "source_ids": [str(normative_id)],
                    "score_threshold": -1.0,
                },
            )

            assert after_delete_status == 200
            assert after_delete_response == {"hits": []}

            section_deleted = client.delete(f"/api/v1/catalog/sections/{section_id}")

            assert section_deleted.status_code == 204

    finally:
        for source_id in source_ids:
            _cleanup_qdrant_source(source_id)

        with (
            suppress(httpx.HTTPError),
            httpx.Client(
                base_url=base_url,
                timeout=10,
            ) as cleanup_client,
        ):
            if len(source_ids) >= 1:
                cleanup_client.delete(f"/api/v1/catalog/normative-documents/{source_ids[0]}")

            if len(source_ids) >= 2:
                cleanup_client.delete(f"/api/v1/catalog/user-documents/{source_ids[1]}")

        _cleanup_database(
            email,
            source_ids,
        )
