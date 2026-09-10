# services/api-gateway/src/api_gateway/transport/routers/api_v1.py

"""Aggregator публичных routers API version v1."""

from fastapi import APIRouter

from api_gateway.transport.routers.auth import router as auth_router
from api_gateway.transport.routers.catalog import router as catalog_router
from api_gateway.transport.routers.catalog_sources import (
    router as catalog_sources_router,
)
from api_gateway.transport.routers.system import router as system_router

router = APIRouter(prefix="/api/v1")

router.include_router(auth_router)
router.include_router(catalog_router)
router.include_router(catalog_sources_router)
router.include_router(system_router)
