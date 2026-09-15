# services/context-service/src/context_service/main.py

"""Runtime entrypoint Context HTTP Service."""

import uvicorn

from context_service.core.settings import (
    load_context_settings,
)
from context_service.transport.app import (
    create_app,
)

settings = load_context_settings()

app = create_app(settings)


def run() -> None:
    """Запускает internal Context HTTP server."""
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    run()
