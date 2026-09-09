# services/api-gateway/src/api_gateway/transport/routers/api_v1.py

"""Aggregator публичных routers API version v1."""

from fastapi import APIRouter

from api_gateway.transport.routers.system import (
    router as system_router,
)

router = APIRouter(
    prefix="/api/v1",
)

router.include_router(system_router)
