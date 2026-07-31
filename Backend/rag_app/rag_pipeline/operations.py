"""Application use cases consumed by CLI and HTTP adapters."""

import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO

from ..core.config import Settings
from ..core.exceptions import UnsupportedDocumentTypeError
from ..core.schemas import (
    Answer,
    IngestResponse,
    KeywordSearchRequest,
    QueryRequest,
    SearchResult,
)
from .service import RAGService


def health_status(settings: Settings) -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


def ingest_uploaded_document(
    service: RAGService,
    stream: BinaryIO,
    filename: str | None,
    namespace: str | None = None,
) -> IngestResponse:
    """Validate, stage, and ingest an uploaded PDF stream."""
    temporary_path: Path | None = None
    try:
        original_name = Path(filename or "").name
        if Path(original_name).suffix.lower() != ".pdf":
            raise UnsupportedDocumentTypeError("Only PDF uploads are supported")
        with NamedTemporaryFile(delete=False, suffix=".pdf") as temporary:
            shutil.copyfileobj(stream, temporary)
            temporary_path = Path(temporary.name)
        return service.ingest_pdf(
            temporary_path,
            namespace=namespace,
            document_name=original_name or "document.pdf",
        )
    finally:
        stream.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def answer_query(service: RAGService, request: QueryRequest) -> Answer:
    return service.answer(
        request.question,
        top_k=request.top_k,
        namespace=request.namespace,
        metadata_filter=request.metadata_filter,
        score_threshold=request.score_threshold,
        search_mode=request.search_mode,
    )


def keyword_search(
    service: RAGService, request: KeywordSearchRequest
) -> list[SearchResult]:
    return service.keyword_search(
        request.query,
        top_k=request.top_k,
        namespace=request.namespace,
        document_id=request.document_id,
    )
