import unittest

from Backend.rag_app.core.config import Settings
from Backend.rag_app.core.schemas import SearchResult
from Backend.rag_app.retrieval.hybrid import HybridRetriever


class FakeVectorStore:
    def query(self, *args, **kwargs):
        return [
            SearchResult(chunk_id="a", score=0.9, text="semantic a", metadata={}),
            SearchResult(chunk_id="b", score=0.8, text="semantic b", metadata={}),
        ]


class FakeRepository:
    def keyword_search(self, *args, **kwargs):
        return [
            SearchResult(chunk_id="b", score=0.7, text="keyword b", metadata={}),
            SearchResult(chunk_id="c", score=0.6, text="keyword c", metadata={}),
        ]

    def get_chunks(self, chunk_ids, *, namespace):
        return {
            chunk_id: SearchResult(
                chunk_id=chunk_id,
                score=0,
                text=f"postgres {chunk_id}",
                metadata={"document_id": "doc_1"},
            )
            for chunk_id in chunk_ids
        }


class HybridRetrieverTests(unittest.TestCase):
    def test_hybrid_search_fuses_and_uses_postgres_text(self) -> None:
        retriever = HybridRetriever(
            Settings(_env_file=None), FakeVectorStore(), FakeRepository()
        )
        results = retriever.search("revenue", mode="hybrid", top_k=3)

        self.assertEqual(results[0].chunk_id, "b")
        self.assertEqual(results[0].text, "postgres b")
        self.assertEqual(results[0].metadata["retrieval_method"], "hybrid")
        self.assertEqual(results[0].score, 1.0)


if __name__ == "__main__":
    unittest.main()
