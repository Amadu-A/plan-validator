# services/auth-service/src/auth_service/main.py

"""Runtime entrypoint Authentication Service."""

import uvicorn

from auth_service.core.settings import (
    load_auth_settings,
)
from auth_service.transport.app import (
    create_app,
)

settings = load_auth_settings()
app = create_app(settings)


def run() -> None:
    """Запускает internal Auth HTTP server."""
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    run()
