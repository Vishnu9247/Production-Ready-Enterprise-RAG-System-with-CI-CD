"""Retrieval-augmented question-answering HTTP endpoint."""

from fastapi import APIRouter, Depends

from ..core.schemas import Answer, QueryRequest
from ..rag_pipeline.factory import get_rag_service
from ..rag_pipeline.operations import answer_query
from ..rag_pipeline.service import RAGService


router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=Answer)
def query(
    request: QueryRequest,
    service: RAGService = Depends(get_rag_service),
) -> Answer:
    return answer_query(service, request)
