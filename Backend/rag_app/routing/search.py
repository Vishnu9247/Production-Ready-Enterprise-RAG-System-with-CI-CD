"""Keyword-search HTTP endpoint."""

from fastapi import APIRouter, Depends

from ..core.schemas import KeywordSearchRequest, SearchResult
from ..rag_pipeline.factory import get_rag_service
from ..rag_pipeline.operations import keyword_search
from ..rag_pipeline.service import RAGService


router = APIRouter(prefix="/search", tags=["search"])


@router.post("/keyword", response_model=list[SearchResult])
def search_keywords(
    request: KeywordSearchRequest,
    service: RAGService = Depends(get_rag_service),
) -> list[SearchResult]:
    return keyword_search(service, request)
