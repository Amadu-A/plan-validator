# services/catalog-service/src/catalog_service/transport/dependencies.py

"""FastAPI dependencies Catalog Service."""

from typing import cast

from fastapi import Request

from catalog_service.core.container import CatalogContainer


def get_container(request: Request) -> CatalogContainer:
    """Возвращает Catalog composition root из FastAPI state."""
    return cast(
        CatalogContainer,
        request.app.state.container,
    )
