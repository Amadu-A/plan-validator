# services/embedding-service/src/embedding_service/main.py

"""Runtime entrypoint Embedding HTTP Service."""

import uvicorn

from embedding_service.core.settings import load_embedding_settings
from embedding_service.transport.app import create_app

settings = load_embedding_settings()
app = create_app(settings)


def run() -> None:
    """Запускает internal operational HTTP server."""
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    run()
