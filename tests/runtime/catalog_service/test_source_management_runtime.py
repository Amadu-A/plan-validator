# tests/runtime/catalog_service/test_source_management_runtime.py

"""Runtime E2E managed N/U sources через Gateway/Auth/Catalog/PostgreSQL."""

import os
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
import psycopg


def cleanup_runtime_records(
    *,
    email: str,
    source_ids: list[UUID],
) -> None:
    """Удаляет test outbox/source/catalog/auth records после E2E."""
    password = os.environ["PLAN_VALIDATOR_POSTGRES_PASSWORD"]
    host_port = int(
        os.environ.get(
            "PLAN_VALIDATOR_POSTGRES_HOST_PORT",
            "5438",
        )
    )

    with (
        psycopg.connect(
            host="127.0.0.1",
            port=host_port,
            dbname="plan_validator",
            user="plan_validator",
            password=password,
        ) as connection,
        connection.cursor() as cursor,
    ):
        for source_id in source_ids:
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
                SELECT id
                FROM auth.users
                WHERE email = %s
            )
            """,
            (email.casefold(),),
        )
        cursor.execute(
            """
            DELETE FROM catalog.sections
            WHERE user_id = (
                SELECT id
                FROM auth.users
                WHERE email = %s
            )
            """,
            (email.casefold(),),
        )
        cursor.execute(
            """
            DELETE FROM catalog.system_prompts
            WHERE user_id = (
                SELECT id
                FROM auth.users
                WHERE email = %s
            )
            """,
            (email.casefold(),),
        )
        cursor.execute(
            "DELETE FROM auth.users WHERE email = %s",
            (email.casefold(),),
        )


def count_outbox_events(source_ids: list[UUID]) -> dict[str, int]:
    """Считает durable source events в real PostgreSQL."""
    password = os.environ["PLAN_VALIDATOR_POSTGRES_PASSWORD"]
    host_port = int(
        os.environ.get(
            "PLAN_VALIDATOR_POSTGRES_HOST_PORT",
            "5438",
        )
    )

    result: dict[str, int] = {}

    with (
        psycopg.connect(
            host="127.0.0.1",
            port=host_port,
            dbname="plan_validator",
            user="plan_validator",
            password=password,
        ) as connection,
        connection.cursor() as cursor,
    ):
        for source_id in source_ids:
            cursor.execute(
                """
                SELECT event_type, COUNT(*)
                FROM catalog.source_outbox_messages
                WHERE source_id = %s
                GROUP BY event_type
                """,
                (source_id,),
            )

            for event_type, count in cursor.fetchall():
                result[str(event_type)] = result.get(str(event_type), 0) + int(count)

    return result


def test_runtime_n_u_storage_lifecycle_and_outbox() -> None:
    """Проверяет upload/content/delete/section guard и transactional outbox."""
    email = f"sources-runtime-{uuid4().hex}@example.com"
    password = "runtime-source-password-123"
    source_ids: list[UUID] = []

    gateway_port = int(
        os.environ.get(
            "PLAN_VALIDATOR_GATEWAY_HOST_PORT",
            "8000",
        )
    )
    base_url = f"http://127.0.0.1:{gateway_port}"
    pdf = b"%PDF-1.7\nplan-validator-stage-7\n"

    try:
        with httpx.Client(
            base_url=base_url,
            timeout=10,
        ) as client:
            registered = client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": password,
                },
            )
            assert registered.status_code == 201

            section = client.post(
                "/api/v1/catalog/sections",
                json={
                    "title": "Stage 7 Sources",
                    "sort_order": 0,
                },
            )
            assert section.status_code == 201
            section_id = section.json()["id"]

            try:
                normative = client.post(
                    "/api/v1/catalog/normative-documents",
                    params={"section_id": section_id},
                    headers={
                        "X-Source-Filename": quote(
                            "СП runtime.pdf",
                            safe="",
                        ),
                        "Content-Type": "application/octet-stream",
                    },
                    content=pdf,
                )
                assert normative.status_code == 201
                assert normative.json()["kind"] == "N"
                assert "storage_key" not in normative.json()
                source_ids.append(UUID(normative.json()["id"]))

                user_source = client.post(
                    "/api/v1/catalog/user-documents",
                    params={"section_id": section_id},
                    headers={
                        "X-Source-Filename": quote(
                            "Письмо runtime.pdf",
                            safe="",
                        ),
                        "Content-Type": "application/octet-stream",
                    },
                    content=pdf,
                )
                assert user_source.status_code == 201
                assert user_source.json()["kind"] == "U"
                source_ids.append(UUID(user_source.json()["id"]))

                n_list = client.get(
                    "/api/v1/catalog/normative-documents",
                    params={"section_id": section_id},
                )
                u_list = client.get(
                    "/api/v1/catalog/user-documents",
                    params={"section_id": section_id},
                )

                assert n_list.status_code == 200
                assert u_list.status_code == 200
                assert len(n_list.json()["sources"]) == 1
                assert len(u_list.json()["sources"]) == 1

                content = client.get(f"/api/v1/catalog/normative-documents/{source_ids[0]}/content")
                assert content.status_code == 200
                assert content.content == pdf

                blocked_section_delete = client.delete(f"/api/v1/catalog/sections/{section_id}")
                assert blocked_section_delete.status_code == 409

                for source_id, resource in (
                    (source_ids[0], "normative-documents"),
                    (source_ids[1], "user-documents"),
                ):
                    deleted = client.delete(f"/api/v1/catalog/{resource}/{source_id}")
                    assert deleted.status_code == 204

                    deleted_again = client.delete(f"/api/v1/catalog/{resource}/{source_id}")
                    assert deleted_again.status_code == 204

                events = count_outbox_events(source_ids)

                assert events["catalog.source.uploaded.v1"] == 2
                assert events["catalog.source.delete_requested.v1"] == 2

                section_deleted = client.delete(f"/api/v1/catalog/sections/{section_id}")
                assert section_deleted.status_code == 204
            finally:
                cleanup_pairs: list[tuple[UUID, str]] = []

                if len(source_ids) >= 1:
                    cleanup_pairs.append(
                        (
                            source_ids[0],
                            "normative-documents",
                        )
                    )

                if len(source_ids) >= 2:
                    cleanup_pairs.append(
                        (
                            source_ids[1],
                            "user-documents",
                        )
                    )

                for source_id, resource in cleanup_pairs:
                    client.delete(f"/api/v1/catalog/{resource}/{source_id}")
    finally:
        cleanup_runtime_records(
            email=email,
            source_ids=source_ids,
        )
