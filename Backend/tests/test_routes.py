import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from Backend.rag_app.api import app
from datetime import datetime, timezone

from Backend.rag_app.core.schemas import (
    Answer,
    IngestResponse,
    SearchResult,
    SessionHistoryResponse,
    SessionResponse,
)
from Backend.rag_app.rag_pipeline.factory import get_rag_service


class FakeRAGService:
    def ingest_pdf(self, pdf_path, *, namespace=None, document_name=None):
        self.upload_existed = Path(pdf_path).is_file()
        self.document_name = document_name
        return IngestResponse(
            document_id="doc_test",
            document_name=document_name,
            chunks_upserted=2,
            namespace=namespace or "default",
        )

    def answer(self, session_id, query, **kwargs):
        self.question = query
        return Answer(
            session_id=session_id,
            query=query,
            resolved_query=query,
            answer="Test answer",
            reason="Test reason",
            references=[],
        )

    def create_session(self, name, namespace):
        now = datetime.now(timezone.utc)
        return SessionResponse(
            session_id="session-1",
            name=name,
            namespace=namespace,
            created_at=now,
            updated_at=now,
        )

    def get_session_history(self, session_id, *, limit=None):
        return SessionHistoryResponse(
            session=self.create_session("Test session", "default"),
            messages=[],
        )

    def keyword_search(self, query_text, **kwargs):
        return [
            SearchResult(
                chunk_id="chunk_1",
                score=0.5,
                text="keyword result",
                metadata={"retrieval_method": "keyword"},
            )
        ]


class RouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FakeRAGService()
        app.dependency_overrides[get_rag_service] = lambda: self.service
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_expected_routes_are_registered(self) -> None:
        paths = set(app.openapi()["paths"])
        self.assertTrue(
            {
                "/health",
                "/v1/documents",
                "/v1/query",
                "/v1/search/keyword",
                "/v1/sessions",
                "/v1/sessions/{session_id}",
            }.issubset(
                paths
            )
        )

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_cors_allows_configured_frontend(self) -> None:
        response = self.client.options(
            "/v1/query",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://localhost:5173",
        )

    def test_pdf_upload(self) -> None:
        response = self.client.post(
            "/v1/documents?namespace=finance",
            files={"file": ("report.pdf", b"%PDF-1.7 test", "application/pdf")},
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(self.service.upload_existed)
        self.assertEqual(response.json()["document_name"], "report.pdf")

    def test_non_pdf_upload_is_rejected(self) -> None:
        response = self.client.post(
            "/v1/documents",
            files={"file": ("notes.txt", b"not a pdf", "text/plain")},
        )
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.json()["detail"], "Only PDF uploads are supported")

    def test_query(self) -> None:
        response = self.client.post(
            "/v1/query",
            json={
                "session_id": "session-1",
                "query": "What changed?",
                "search_mode": "hybrid",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "Test answer")

    def test_session_creation_and_history(self) -> None:
        created = self.client.post(
            "/v1/sessions",
            json={"name": "Test session", "namespace": "default"},
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["session_id"], "session-1")

        history = self.client.get("/v1/sessions/session-1")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["messages"], [])

    def test_keyword_search(self) -> None:
        response = self.client.post(
            "/v1/search/keyword", json={"query": "revenue", "top_k": 3}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["text"], "keyword result")


if __name__ == "__main__":
    unittest.main()
