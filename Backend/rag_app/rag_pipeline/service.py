"""End-to-end ingestion and grounded question answering."""

from pathlib import Path
from typing import Any

from ..core.config import Settings
from ..core.schemas import Answer, Citation, IngestResponse, SearchResult
from ..document_extraction.chunking import chunk_document
from ..document_extraction.extractor import extract_document
from ..document_storage.base import DocumentStorage
from ..document_storage.factory import create_document_storage
from ..database.repository import PostgresDocumentRepository
from ..embedding_generation.service import AzureOpenAIService
from ..retrieval.hybrid import HybridRetriever, SearchMode
from ..vector_store_operations.pinecone_store import PineconeVectorStore


SYSTEM_PROMPT = """You answer questions using only the supplied context.
If the context does not contain enough information, say that you do not know.
Use inline citations such as [1] and [2] that correspond to the numbered context blocks.
Do not invent citations, facts, or sources."""


class RAGService:
    def __init__(
        self,
        settings: Settings,
        azure: AzureOpenAIService | None = None,
        vector_store: PineconeVectorStore | None = None,
        document_repository: PostgresDocumentRepository | None = None,
        document_storage: DocumentStorage | None = None,
        retriever: HybridRetriever | None = None,
    ) -> None:
        self.settings = settings
        self.azure = azure or AzureOpenAIService(settings)
        self.vector_store = vector_store or PineconeVectorStore(settings, self.azure)
        self.document_repository = document_repository
        if self.document_repository is None and settings.database_configured:
            self.document_repository = PostgresDocumentRepository(settings)
        self.document_storage = document_storage or create_document_storage(settings)
        self.retriever = retriever or HybridRetriever(
            settings, self.vector_store, self.document_repository
        )

    def ingest_pdf(
        self,
        pdf_path: str | Path,
        *,
        namespace: str | None = None,
        document_name: str | None = None,
    ) -> IngestResponse:
        metadata = extract_document(
            pdf_path,
            self.settings.data_directory / "documents",
            document_name=document_name,
        )
        document_directory = Path(metadata["blocks_path"]).parent
        chunks = chunk_document(
            document_directory,
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
        )
        target_namespace = namespace or self.settings.pinecone_namespace
        storage_uri = self.document_storage.upload_pdf(
            Path(pdf_path), metadata["document_id"], metadata["document_name"]
        )
        if self.document_repository is not None:
            self.document_repository.save_document(
                metadata,
                chunks,
                storage_uri=storage_uri,
                namespace=target_namespace,
            )
        try:
            count = self.vector_store.upsert_chunks(chunks, namespace=target_namespace)
        except Exception:
            if self.document_repository is not None:
                self.document_repository.update_document_status(metadata["document_id"], "failed")
            raise
        if self.document_repository is not None:
            self.document_repository.update_document_status(metadata["document_id"], "indexed")
        return IngestResponse(
            document_id=metadata["document_id"],
            document_name=metadata["document_name"],
            chunks_upserted=count,
            namespace=target_namespace,
            storage_uri=storage_uri,
        )

    def answer(
        self,
        question: str,
        *,
        top_k: int | None = None,
        namespace: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
        score_threshold: float | None = None,
        search_mode: SearchMode = "hybrid",
    ) -> Answer:
        sources = self.retriever.search(
            question,
            mode=search_mode,
            top_k=top_k,
            namespace=namespace,
            metadata_filter=metadata_filter,
            score_threshold=score_threshold,
        )
        if not sources:
            return Answer(
                answer="I do not know based on the indexed documents.", citations=[], sources=[]
            )
        context = "\n\n".join(
            f"[{number}] {source.text}" for number, source in enumerate(sources, start=1)
        )
        response = self.azure.complete(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
            ]
        )
        return Answer(
            answer=response,
            citations=[self._citation(number, source) for number, source in enumerate(sources, 1)],
            sources=sources,
        )

    def keyword_search(
        self,
        query_text: str,
        *,
        top_k: int | None = None,
        namespace: str | None = None,
        document_id: str | None = None,
    ) -> list[SearchResult]:
        metadata_filter = {"document_id": {"$eq": document_id}} if document_id else None
        return self.retriever.search(
            query_text,
            mode="keyword",
            top_k=top_k,
            namespace=namespace,
            metadata_filter=metadata_filter,
        )

    @staticmethod
    def _citation(number: int, source: SearchResult) -> Citation:
        raw_pages = source.metadata.get("page_numbers", [])
        pages = []
        for page in raw_pages if isinstance(raw_pages, list) else [raw_pages]:
            try:
                pages.append(int(float(page)))
            except (TypeError, ValueError):
                continue
        return Citation(
            number=number,
            chunk_id=source.chunk_id,
            document_id=str(source.metadata.get("document_id", "")),
            document_name=str(source.metadata.get("document_name", "")),
            page_numbers=pages,
            score=source.score,
        )
