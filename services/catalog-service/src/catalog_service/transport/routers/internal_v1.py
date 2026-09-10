# services/catalog-service/src/catalog_service/transport/routers/internal_v1.py

"""Aggregator internal API version v1 Catalog Service."""

from fastapi import APIRouter

from catalog_service.transport.routers.catalog import router as catalog_router
from catalog_service.transport.routers.normative_documents import (
    router as normative_documents_router,
)
from catalog_service.transport.routers.user_documents import (
    router as user_documents_router,
)

router = APIRouter(prefix="/internal/v1")
router.include_router(catalog_router)
router.include_router(normative_documents_router)
router.include_router(user_documents_router)
