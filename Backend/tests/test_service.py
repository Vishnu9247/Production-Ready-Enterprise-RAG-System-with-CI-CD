import unittest

from Backend.rag_app.core.config import Settings
from Backend.rag_app.core.schemas import SearchResult
from Backend.rag_app.rag_pipeline.service import RAGService


class FakeAzure:
    def complete(self, messages, *, temperature=0.0):
        self.messages = messages
        return "Revenue increased by ten percent [1]."


class FakeStore:
    def query(self, *args, **kwargs):
        return [
            SearchResult(
                chunk_id="doc_1_chunk_1",
                score=0.91,
                text="Revenue increased by ten percent.",
                metadata={
                    "document_id": "doc_1",
                    "document_name": "report.pdf",
                    "page_numbers": ["3"],
                },
            )
        ]


class RAGServiceTests(unittest.TestCase):
    def test_answer_contains_citation_details(self) -> None:
        service = RAGService(
            Settings(_env_file=None), azure=FakeAzure(), vector_store=FakeStore()
        )
        result = service.answer("How did revenue change?")

        self.assertIn("[1]", result.answer)
        self.assertEqual(result.citations[0].page_numbers, [3])
        self.assertEqual(result.citations[0].document_name, "report.pdf")


if __name__ == "__main__":
    unittest.main()
