# tests/runtime/auth_service/test_auth_runtime.py

"""Runtime E2E browser-like auth flow через реальный API Gateway/PostgreSQL."""

import os
from uuid import uuid4

import httpx
import psycopg


def cleanup_test_user(
    email: str,
) -> None:
    """Удаляет созданного E2E user и cascade sessions после test."""
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
        cursor.execute(
            ("DELETE FROM auth.users WHERE email = %s"),
            (email.casefold(),),
        )


def test_runtime_registration_login_cookie_and_logout() -> None:
    """Проверяет полный public auth flow без остаточных test records."""
    email = f"runtime-{uuid4().hex}@example.com"
    password = "runtime-strong-password-123"

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
            register = client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": password,
                },
            )

            assert register.status_code == 201
            assert "session_token" not in register.text
            assert "HttpOnly" in register.headers["set-cookie"]

            duplicate = client.post(
                "/api/v1/auth/register",
                json={
                    "email": email.upper(),
                    "password": password,
                },
            )

            assert duplicate.status_code == 409

            me = client.get("/api/v1/auth/me")

            assert me.status_code == 200
            assert me.json()["email"] == email

            logout = client.post("/api/v1/auth/logout")

            assert logout.status_code == 204

            after_logout = client.get("/api/v1/auth/me")

            assert after_logout.status_code == 401

            wrong_login = client.post(
                "/api/v1/auth/login",
                json={
                    "email": email,
                    "password": ("wrong-password-123"),
                },
            )

            assert wrong_login.status_code == 401

            valid_login = client.post(
                "/api/v1/auth/login",
                json={
                    "email": email,
                    "password": password,
                },
            )

            assert valid_login.status_code == 200

            authenticated_me = client.get("/api/v1/auth/me")

            assert authenticated_me.status_code == 200
    finally:
        cleanup_test_user(email)
