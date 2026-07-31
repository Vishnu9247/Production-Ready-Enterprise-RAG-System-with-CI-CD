"""Document ingestion HTTP endpoint."""

from fastapi import APIRouter, Depends, File, UploadFile, status

from ..core.schemas import IngestResponse
from ..rag_pipeline.factory import get_rag_service
from ..rag_pipeline.operations import ingest_uploaded_document
from ..rag_pipeline.service import RAGService


router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
def ingest_document(
    file: UploadFile = File(...),
    namespace: str | None = None,
    service: RAGService = Depends(get_rag_service),
) -> IngestResponse:
    return ingest_uploaded_document(service, file.file, file.filename, namespace)
