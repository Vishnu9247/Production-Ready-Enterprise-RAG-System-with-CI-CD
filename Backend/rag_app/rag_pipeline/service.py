"""End-to-end ingestion and LangGraph-powered grounded question answering."""

from pathlib import Path
from typing import Any

from ..core.config import Settings
from ..agents import QueryWorkflow
from ..agents.state import QueryWorkflowState
from ..core.schemas import (
    Answer,
    IngestResponse,
    SearchResult,
    SessionHistoryResponse,
    SessionResponse,
)
from ..database.conversation_repository import ConversationRepository
from ..document_extraction.chunking import chunk_document
from ..document_extraction.extractor import extract_document
from ..document_storage.base import DocumentStorage
from ..document_storage.factory import create_document_storage
from ..database.repository import PostgresDocumentRepository
from ..embedding_generation.service import AzureOpenAIService
from ..retrieval.hybrid import HybridRetriever, SearchMode
from ..vector_store_operations.pinecone_store import PineconeVectorStore


class RAGService:
    def __init__(
        self,
        settings: Settings,
        azure: AzureOpenAIService | None = None,
        vector_store: PineconeVectorStore | None = None,
        document_repository: PostgresDocumentRepository | None = None,
        document_storage: DocumentStorage | None = None,
        retriever: HybridRetriever | None = None,
        conversations: ConversationRepository | None = None,
        query_workflow: QueryWorkflow | None = None,
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
        self.conversations = conversations
        if self.conversations is None and settings.database_configured:
            session_factory = (
                self.document_repository.session_factory
                if self.document_repository is not None
                else None
            )
            self.conversations = ConversationRepository(settings, session_factory)
        self.query_workflow = query_workflow
        if self.query_workflow is None and self.conversations is not None:
            self.query_workflow = QueryWorkflow(
                settings,
                self.azure,
                self.conversations,
                self.retriever,
            )

    def ingest_pdf(
        self,
        pdf_path: str | Path,
        *,
        namespace: str | None = None,
        document_name: str | None = None,
    ) -> IngestResponse:
        self.settings.require_llama_cloud()
        metadata = extract_document(
            pdf_path,
            self.settings.data_directory / "documents",
            api_key=self.settings.llama_cloud_api_key.get_secret_value(),
            tier=self.settings.llama_parse_tier,
            version=self.settings.llama_parse_version,
            timeout_seconds=self.settings.llama_parse_timeout_seconds,
            organization_id=self.settings.llama_cloud_organization_id or None,
            project_id=self.settings.llama_cloud_project_id or None,
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
        session_id: str,
        query: str,
        *,
        top_k: int | None = None,
        metadata_filter: dict[str, Any] | None = None,
        score_threshold: float | None = None,
        search_mode: SearchMode = "hybrid",
    ) -> Answer:
        if self.conversations is None or self.query_workflow is None:
            raise RuntimeError("PostgreSQL is required for session-based querying")
        session = self.conversations.get_session(session_id)
        state: QueryWorkflowState = {
            "session_id": session_id,
            "namespace": session.namespace,
            "query": query,
            "search_mode": search_mode,
            "top_k": top_k,
            "metadata_filter": metadata_filter,
            "score_threshold": score_threshold,
        }
        result = self.query_workflow.invoke(state)
        answer = Answer(
            session_id=session_id,
            query=query,
            resolved_query=result["resolved_query"],
            answer=result["answer"],
            reason=result["reason"],
            references=result.get("references", []),
        )
        messages = self.conversations.append_exchange(
            session_id=session_id,
            query=query,
            resolved_query=answer.resolved_query,
            answer=answer.answer,
            reason=answer.reason,
            references=answer.references,
        )
        self.vector_store.upsert_history_messages(messages)
        return answer

    def create_session(self, name: str, namespace: str) -> SessionResponse:
        if self.conversations is None:
            raise RuntimeError("PostgreSQL is required for conversation sessions")
        return self.conversations.create_session(name, namespace)

    def get_session_history(
        self, session_id: str, *, limit: int | None = None
    ) -> SessionHistoryResponse:
        if self.conversations is None:
            raise RuntimeError("PostgreSQL is required for conversation sessions")
        session = self.conversations.get_session(session_id)
        messages = self.conversations.list_messages(
            session_id,
            limit=limit or self.settings.history_max_messages,
        )
        return SessionHistoryResponse(session=session, messages=messages)

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
