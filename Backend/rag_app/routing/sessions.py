"""Thin HTTP routes for durable conversation sessions."""

from fastapi import APIRouter, Depends, Query, status

from ..core.schemas import SessionCreateRequest, SessionHistoryResponse, SessionResponse
from ..rag_pipeline.factory import get_rag_service
from ..rag_pipeline.operations import create_session, get_session_history
from ..rag_pipeline.service import RAGService


router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create(
    request: SessionCreateRequest,
    service: RAGService = Depends(get_rag_service),
) -> SessionResponse:
    return create_session(service, request)


@router.get("/{session_id}", response_model=SessionHistoryResponse)
def history(
    session_id: str,
    limit: int | None = Query(default=None, ge=1, le=100),
    service: RAGService = Depends(get_rag_service),
) -> SessionHistoryResponse:
    return get_session_history(service, session_id, limit)
