# services/api-gateway/src/api_gateway/main.py

"""Runtime entrypoint API Gateway Plan Validator."""

import uvicorn

from api_gateway.core.settings import (
    load_gateway_settings,
)
from api_gateway.transport.app import (
    create_app,
)

settings = load_gateway_settings()
app = create_app(settings)


def run() -> None:
    """Запускает Uvicorn с project logging вместо duplicate access logging."""
    uvicorn.run(
        app,
        host=settings.gateway.host,
        port=settings.gateway.port,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    run()
