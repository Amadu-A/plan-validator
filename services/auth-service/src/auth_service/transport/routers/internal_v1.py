# services/auth-service/src/auth_service/transport/routers/internal_v1.py

"""Aggregator internal API version v1 Authentication Service."""

from fastapi import APIRouter

from auth_service.transport.routers.auth import (
    router as auth_router,
)

router = APIRouter(prefix="/internal/v1")

router.include_router(auth_router)
