import unittest
from types import SimpleNamespace

from Backend.rag_app.core.config import Settings
from Backend.rag_app.core.schemas import Chunk
from Backend.rag_app.vector_store_operations.pinecone_store import (
    PineconeVectorStore,
    prepare_metadata,
)


class FakeEmbeddings:
    def embed_query(self, text):
        return [0.1, 0.2]


class FakeIndex:
    def query(self, **kwargs):
        self.query_kwargs = kwargs
        return SimpleNamespace(
            matches=[
                SimpleNamespace(
                    id="chunk_1",
                    score=0.8,
                    metadata={"text": "source text", "document_id": "doc_1"},
                )
            ]
        )


class FakePinecone:
    def __init__(self):
        self.data_index = FakeIndex()

    def has_index(self, name):
        return True

    def describe_index(self, name):
        return SimpleNamespace(dimension=2)

    def index(self, name=None, *, host=None):
        self.index_name = name
        self.index_host = host
        return self.data_index


class VectorStoreTests(unittest.TestCase):
    def test_query_maps_pinecone_match(self) -> None:
        store = PineconeVectorStore(
            Settings(_env_file=None, embedding_dimensions=2),
            FakeEmbeddings(),
            client=FakePinecone(),
        )
        results = store.query("question", score_threshold=0.7)

        self.assertEqual(results[0].text, "source text")
        self.assertEqual(results[0].metadata["document_id"], "doc_1")
        self.assertNotIn("text", results[0].metadata)

    def test_metadata_is_flat_and_omits_empty_lists(self) -> None:
        metadata = prepare_metadata(
            Chunk(chunk_id="chunk_1", text="text", metadata={"pages": [1, 2], "empty": []})
        )
        self.assertEqual(metadata["pages"], ["1", "2"])
        self.assertNotIn("empty", metadata)

    def test_configured_host_bypasses_index_control_plane(self) -> None:
        client = FakePinecone()
        store = PineconeVectorStore(
            Settings(
                _env_file=None,
                embedding_dimensions=2,
                pinecone_host="configured-index.svc.pinecone.io",
            ),
            FakeEmbeddings(),
            client=client,
        )
        store.ensure_index()
        self.assertEqual(client.index_host, "configured-index.svc.pinecone.io")


if __name__ == "__main__":
    unittest.main()
