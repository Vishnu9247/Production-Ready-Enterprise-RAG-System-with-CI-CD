import json
import tempfile
import unittest
from pathlib import Path

from Backend.rag_app.document_extraction.chunking import chunk_document


class ChunkDocumentTests(unittest.TestCase):
    def test_chunks_preserve_source_metadata_and_have_stable_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "document_metadata.json").write_text(
                json.dumps({"document_id": "doc_test", "document_name": "report.pdf"}),
                encoding="utf-8",
            )
            blocks = [
                {"type": "heading", "text": "Revenue", "heading_level": 1},
                {
                    "type": "text",
                    "text": "Revenue increased by ten percent.",
                    "block_id": "block_1",
                    "text_id": "text_1",
                    "page_number": 3,
                },
                {
                    "type": "table",
                    "table_markdown": "| Year | Revenue |\n| 2025 | 10 |",
                    "block_id": "block_2",
                    "table_id": "table_1",
                    "page_number": 3,
                },
            ]
            (directory / "blocks.json").write_text(json.dumps(blocks), encoding="utf-8")

            chunks = chunk_document(directory, chunk_size=500, chunk_overlap=50)

            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0].chunk_id, "doc_test_chunk_000001")
            self.assertIn("Revenue increased", chunks[0].text)
            self.assertEqual(chunks[0].metadata["page_numbers"], [3])
            self.assertEqual(chunks[0].metadata["table_ids"], ["table_1"])
            self.assertTrue((directory / "chunks.json").is_file())

    def test_rejects_overlap_larger_than_chunk(self) -> None:
        with self.assertRaises(ValueError):
            chunk_document("unused", chunk_size=200, chunk_overlap=200)


if __name__ == "__main__":
    unittest.main()
