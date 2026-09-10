# services/retrieval-service/src/retrieval_service/main.py

"""Runtime entrypoint Retrieval HTTP Service."""

import uvicorn

from retrieval_service.core.settings import load_retrieval_settings
from retrieval_service.transport.app import create_app

settings = load_retrieval_settings()
app = create_app(settings)


def run() -> None:
    """Запускает internal operational/retrieval HTTP server."""
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    run()
