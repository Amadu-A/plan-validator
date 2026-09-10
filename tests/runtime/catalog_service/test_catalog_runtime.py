# tests/runtime/catalog_service/test_catalog_runtime.py

"""Runtime E2E Catalog через real Gateway/Auth/Catalog/PostgreSQL."""

import os
from uuid import uuid4

import httpx
import psycopg


def cleanup_runtime_user(email: str) -> None:
    """Удаляет Catalog/Auth records созданного E2E пользователя."""
    password = os.environ["PLAN_VALIDATOR_POSTGRES_PASSWORD"]
    host_port = int(
        os.environ.get(
            "PLAN_VALIDATOR_POSTGRES_HOST_PORT",
            "5438",
        )
    )

    with psycopg.connect(
        host="127.0.0.1",
        port=host_port,
        dbname="plan_validator",
        user="plan_validator",
        password=password,
    ) as connection:
        with connection.cursor() as cursor:
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


def test_runtime_nested_catalog_and_system_prompt() -> None:
    """Проверяет auth ownership, hierarchy, prompt и delete cascade."""
    email = f"catalog-runtime-{uuid4().hex}@example.com"
    password = "runtime-catalog-password-123"

    gateway_port = int(
        os.environ.get(
            "PLAN_VALIDATOR_GATEWAY_HOST_PORT",
            "8000",
        )
    )

    base_url = f"http://127.0.0.1:{gateway_port}"

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

            root_response = client.post(
                "/api/v1/catalog/sections",
                json={
                    "title": "Нормативная база",
                    "sort_order": 0,
                },
            )

            assert root_response.status_code == 201
            root_id = root_response.json()["id"]

            child_response = client.post(
                "/api/v1/catalog/sections",
                json={
                    "title": "СП",
                    "parent_id": root_id,
                    "sort_order": 0,
                },
            )

            assert child_response.status_code == 201
            child_id = child_response.json()["id"]

            cycle_response = client.patch(
                f"/api/v1/catalog/sections/{root_id}",
                json={"parent_id": child_id},
            )

            assert cycle_response.status_code == 400

            listed = client.get("/api/v1/catalog/sections")

            assert listed.status_code == 200
            assert len(listed.json()["sections"]) == 2

            saved_prompt = client.put(
                "/api/v1/catalog/system-prompt",
                json={
                    "prompt": (
                        "Проверяй проект строго по найденной "
                        "нормативной базе."
                    )
                },
            )

            assert saved_prompt.status_code == 200

            loaded_prompt = client.get(
                "/api/v1/catalog/system-prompt"
            )

            assert loaded_prompt.status_code == 200
            assert (
                loaded_prompt.json()["prompt"]
                == saved_prompt.json()["prompt"]
            )

            deleted = client.delete(
                f"/api/v1/catalog/sections/{root_id}"
            )

            assert deleted.status_code == 204

            after_delete = client.get(
                "/api/v1/catalog/sections"
            )

            assert after_delete.status_code == 200
            assert after_delete.json()["sections"] == []
    finally:
        cleanup_runtime_user(email)
