# tests/transport/api_gateway/test_auth.py

"""Transport tests public Gateway authentication cookie contract."""

from datetime import (
    UTC,
    datetime,
)
from pathlib import Path
from uuid import uuid4

from api_gateway.application.auth_service import (
    AuthSession,
    AuthUser,
)
from api_gateway.core.settings import (
    GatewaySettings,
)
from api_gateway.transport.app import (
    create_app,
)
from fastapi.testclient import (
    TestClient,
)
from plan_validator_common.settings import (
    Environment,
)


class FakeAuthServiceClient:
    """Deterministic AuthServiceClient transport-test double."""

    def __init__(self) -> None:
        """Создаёт одного fake authenticated user."""
        self.user = AuthUser(
            id=uuid4(),
            email="ivan@example.com",
            created_at=datetime(
                2026,
                9,
                9,
                tzinfo=UTC,
            ),
        )
        self.token = "test-session-token"

    async def register_user(
        self,
        *,
        email: str,
        password: str,
    ) -> AuthSession:
        """Возвращает fake session для registration."""
        del email
        del password

        return self._session()

    async def login_user(
        self,
        *,
        email: str,
        password: str,
    ) -> AuthSession:
        """Возвращает fake session для login."""
        del email
        del password

        return self._session()

    async def logout_session(
        self,
        *,
        session_token: str,
    ) -> None:
        """Принимает fake logout token."""
        assert session_token == self.token

    async def get_current_user(
        self,
        *,
        session_token: str,
    ) -> AuthUser:
        """Возвращает fake user при ожидаемом token."""
        assert session_token == self.token
        return self.user

    async def aclose(self) -> None:
        """Fake client не имеет network resources."""

    def _session(self) -> AuthSession:
        """Создаёт fake AuthSession."""
        return AuthSession(
            user=self.user,
            session_token=self.token,
            expires_at=datetime(
                2026,
                9,
                16,
                tzinfo=UTC,
            ),
        )


def test_login_cookie_me_and_logout_flow(
    tmp_path: Path,
) -> None:
    """Проверяет token только в HttpOnly cookie и удаление при logout."""
    settings = GatewaySettings(
        environment=Environment.TEST,
        log_to_file=False,
        log_root_dir=tmp_path,
        _env_file=None,
    )

    app = create_app(settings)

    fake_auth = FakeAuthServiceClient()
    app.state.container.auth_service = fake_auth

    with TestClient(app) as client:
        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "ivan@example.com",
                "password": "strong-password-123",
            },
        )

        assert login_response.status_code == 200
        assert "session_token" not in login_response.text

        set_cookie = login_response.headers["set-cookie"]

        assert "plan_validator_session=" in set_cookie
        assert "HttpOnly" in set_cookie

        me_response = client.get("/api/v1/auth/me")

        assert me_response.status_code == 200
        assert me_response.json()["email"] == "ivan@example.com"

        logout_response = client.post("/api/v1/auth/logout")

        assert logout_response.status_code == 204

        unauthorized_response = client.get("/api/v1/auth/me")

        assert unauthorized_response.status_code == 401
