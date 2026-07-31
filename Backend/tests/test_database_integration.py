import os
import unittest
import uuid

from Backend.rag_app.core.config import Settings
from Backend.rag_app.core.schemas import Chunk, Reference
from Backend.rag_app.database.conversation_repository import ConversationRepository
from Backend.rag_app.database.repository import PostgresDocumentRepository


@unittest.skipUnless(
    os.getenv("RUN_POSTGRES_INTEGRATION") == "1",
    "PostgreSQL integration test is enabled in CI",
)
class PostgresIntegrationTests(unittest.TestCase):
    def test_document_persistence_and_keyword_search(self) -> None:
        repository = PostgresDocumentRepository(Settings(_env_file=None))
        repository.initialize_schema()
        suffix = uuid.uuid4().hex[:12]
        document_id = f"doc_{suffix}"
        chunks = [
            Chunk(
                chunk_id=f"{document_id}_chunk_000001",
                text="Quarterly revenue increased significantly.",
                metadata={"document_id": document_id, "chunk_index": 1},
            ),
            Chunk(
                chunk_id=f"{document_id}_chunk_000002",
                text="The company opened a new office.",
                metadata={"document_id": document_id, "chunk_index": 2},
            ),
        ]
        try:
            repository.save_document(
                {"document_id": document_id, "document_name": "report.pdf"},
                chunks,
                storage_uri="https://storage/report.pdf",
                namespace="test",
            )
            results = repository.keyword_search(
                "revenue", namespace="test", top_k=5, document_id=document_id
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].chunk_id, chunks[0].chunk_id)
        finally:
            repository.delete_document(document_id)

    def test_session_and_message_history_persistence(self) -> None:
        settings = Settings(_env_file=None)
        documents = PostgresDocumentRepository(settings)
        documents.initialize_schema()
        conversations = ConversationRepository(
            settings, documents.session_factory
        )
        session = conversations.create_session("Integration", "test")
        try:
            conversations.append_exchange(
                session_id=session.session_id,
                query="What changed?",
                resolved_query="What changed in the report?",
                answer="Revenue increased [1].",
                reason="The cited chunk reports an increase.",
                references=[
                    Reference(
                        number=1,
                        chunk_id="chunk-1",
                        document_name="report.pdf",
                        score=0.9,
                    )
                ],
            )
            history = conversations.list_messages(session.session_id, limit=10)
            self.assertEqual([message.role for message in history], ["user", "assistant"])
            self.assertEqual(history[1].references[0].document_name, "report.pdf")
        finally:
            conversations.delete_session(session.session_id)


if __name__ == "__main__":
    unittest.main()
