# services/document-service/src/document_service/main.py

"""Runtime entrypoint Document HTTP Service."""

import uvicorn

from document_service.core.settings import load_document_settings
from document_service.transport.app import create_app

settings = load_document_settings()
app = create_app(settings)


def run() -> None:
    """Запускает internal Document HTTP server."""
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    run()
