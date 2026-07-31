"""Document persistence and PostgreSQL full-text keyword search."""

from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import Settings
from ..core.schemas import Chunk, SearchResult
from .models import Base, DocumentChunkRecord, DocumentRecord
from .session import create_postgres_engine, create_session_factory


class PostgresDocumentRepository:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory or create_session_factory(settings)

    def initialize_schema(self) -> None:
        engine = self.session_factory.kw.get("bind") or create_postgres_engine(self.settings)
        Base.metadata.create_all(engine)

    def save_document(
        self,
        document_metadata: dict[str, Any],
        chunks: Iterable[Chunk],
        *,
        storage_uri: str | None,
        namespace: str,
        status: str = "processing",
    ) -> None:
        items = list(chunks)
        document_id = str(document_metadata["document_id"])
        with self.session_factory.begin() as session:
            document = session.get(DocumentRecord, document_id)
            if document is None:
                document = DocumentRecord(document_id=document_id)
                session.add(document)
            document.document_name = str(document_metadata.get("document_name", ""))
            document.storage_uri = storage_uri
            document.content_type = "application/pdf"
            document.status = status
            document.attributes = dict(document_metadata)

            session.execute(
                delete(DocumentChunkRecord).where(
                    DocumentChunkRecord.document_id == document_id,
                    DocumentChunkRecord.namespace == namespace,
                )
            )
            session.add_all(
                DocumentChunkRecord(
                    chunk_id=chunk.chunk_id,
                    document_id=document_id,
                    namespace=namespace,
                    chunk_index=int(chunk.metadata.get("chunk_index", index)),
                    text=chunk.text,
                    attributes=dict(chunk.metadata),
                )
                for index, chunk in enumerate(items, start=1)
            )

    def update_document_status(self, document_id: str, status: str) -> None:
        with self.session_factory.begin() as session:
            document = session.get(DocumentRecord, document_id)
            if document is not None:
                document.status = status

    def delete_document(self, document_id: str) -> None:
        with self.session_factory.begin() as session:
            session.execute(
                delete(DocumentRecord).where(DocumentRecord.document_id == document_id)
            )

    def keyword_search(
        self,
        query_text: str,
        *,
        namespace: str,
        top_k: int,
        document_id: str | None = None,
    ) -> list[SearchResult]:
        search_query = func.websearch_to_tsquery("english", query_text)
        rank = func.ts_rank_cd(DocumentChunkRecord.search_vector, search_query).label("rank")
        statement = (
            select(DocumentChunkRecord, DocumentRecord, rank)
            .join(DocumentRecord, DocumentRecord.document_id == DocumentChunkRecord.document_id)
            .where(
                DocumentChunkRecord.namespace == namespace,
                DocumentChunkRecord.search_vector.bool_op("@@")(search_query),
            )
            .order_by(rank.desc())
            .limit(top_k)
        )
        if document_id:
            statement = statement.where(DocumentChunkRecord.document_id == document_id)

        with self.session_factory() as session:
            rows = session.execute(statement).all()
        return [
            SearchResult(
                chunk_id=chunk.chunk_id,
                score=float(score),
                text=chunk.text,
                metadata=dict(chunk.attributes)
                | {
                    "document_id": document.document_id,
                    "document_name": document.document_name,
                    "storage_uri": document.storage_uri or "",
                    "retrieval_method": "keyword",
                },
            )
            for chunk, document, score in rows
        ]

    def get_chunks(
        self, chunk_ids: Iterable[str], *, namespace: str
    ) -> dict[str, SearchResult]:
        ids = list(dict.fromkeys(chunk_ids))
        if not ids:
            return {}
        statement = (
            select(DocumentChunkRecord, DocumentRecord)
            .join(DocumentRecord, DocumentRecord.document_id == DocumentChunkRecord.document_id)
            .where(
                DocumentChunkRecord.chunk_id.in_(ids),
                DocumentChunkRecord.namespace == namespace,
            )
        )
        with self.session_factory() as session:
            rows = session.execute(statement).all()
        return {
            chunk.chunk_id: SearchResult(
                chunk_id=chunk.chunk_id,
                score=0.0,
                text=chunk.text,
                metadata=dict(chunk.attributes)
                | {
                    "document_id": document.document_id,
                    "document_name": document.document_name,
                    "storage_uri": document.storage_uri or "",
                },
            )
            for chunk, document in rows
        }
