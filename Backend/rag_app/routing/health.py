"""Health HTTP endpoint."""

from fastapi import APIRouter, Depends

from ..core.config import Settings, get_settings
from ..rag_pipeline.operations import health_status


router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return health_status(settings)
