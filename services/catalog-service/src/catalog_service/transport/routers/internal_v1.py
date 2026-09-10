# services/catalog-service/src/catalog_service/transport/routers/internal_v1.py

"""Aggregator internal API version v1 Catalog Service."""

from fastapi import APIRouter

from catalog_service.transport.routers.catalog import router as catalog_router

router = APIRouter(prefix="/internal/v1")
router.include_router(catalog_router)
