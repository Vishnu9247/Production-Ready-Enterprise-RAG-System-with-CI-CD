"""FastAPI route registration."""

from fastapi import APIRouter

from . import documents, health, query, search, sessions


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(documents.router, prefix="/v1")
api_router.include_router(query.router, prefix="/v1")
api_router.include_router(search.router, prefix="/v1")
api_router.include_router(sessions.router, prefix="/v1")

__all__ = ["api_router"]
