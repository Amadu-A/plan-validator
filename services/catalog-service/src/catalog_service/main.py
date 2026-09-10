# services/catalog-service/src/catalog_service/main.py

"""Runtime entrypoint Catalog Service."""

import uvicorn

from catalog_service.core.settings import load_catalog_settings
from catalog_service.transport.app import create_app

settings = load_catalog_settings()
app = create_app(settings)


def run() -> None:
    """Запускает internal Catalog HTTP server."""
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    run()
