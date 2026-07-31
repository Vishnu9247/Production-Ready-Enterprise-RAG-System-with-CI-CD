import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from Backend.rag_app.document_extraction.extractor import extract_document


class FakeFiles:
    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(id="file-123")


class FakeParsing:
    def __init__(self, result):
        self.result = result

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return self.result


class FakeClient:
    def __init__(self, result):
        self.files = FakeFiles()
        self.parsing = FakeParsing(result)


class LlamaCloudExtractorTests(unittest.TestCase):
    def test_structured_items_are_normalized_with_page_metadata(self) -> None:
        items = [
            SimpleNamespace(type="heading", value="Revenue", md="# Revenue", level=1),
            SimpleNamespace(
                type="text",
                value="Revenue increased by ten percent.",
                md="Revenue increased by ten percent.",
            ),
            SimpleNamespace(
                type="table",
                md="| Year | Revenue |\n|---|---|\n| 2025 | 10 |",
                csv="Year,Revenue\n2025,10",
            ),
            SimpleNamespace(
                type="image",
                caption="Revenue chart",
                md="![Revenue chart](chart.png)",
                url="chart.png",
            ),
        ]
        result = SimpleNamespace(
            job=SimpleNamespace(id="job-123"),
            items=SimpleNamespace(
                pages=[SimpleNamespace(success=True, page_number=3, items=items)]
            ),
            markdown=SimpleNamespace(
                pages=[
                    SimpleNamespace(
                        success=True,
                        page_number=3,
                        markdown="# Revenue\n\nRevenue increased by ten percent.",
                    )
                ]
            ),
            text=SimpleNamespace(
                pages=[
                    SimpleNamespace(
                        page_number=3, text="Revenue increased by ten percent."
                    )
                ]
            ),
            markdown_full=None,
            text_full=None,
        )
        client = FakeClient(result)

        with tempfile.TemporaryDirectory() as temporary:
            pdf_path = Path(temporary) / "report.pdf"
            pdf_path.write_bytes(b"%PDF-1.7 test")
            metadata = extract_document(
                pdf_path,
                Path(temporary) / "output",
                api_key="test-key",
                client=client,
                document_name="annual-report.pdf",
            )
            blocks = json.loads(Path(metadata["blocks_path"]).read_text(encoding="utf-8"))

        self.assertEqual(metadata["parser"], "llama_cloud")
        self.assertEqual(metadata["document_name"], "annual-report.pdf")
        self.assertEqual(metadata["llama_cloud_file_id"], "file-123")
        self.assertEqual(metadata["llama_cloud_job_id"], "job-123")
        self.assertEqual([block["type"] for block in blocks], ["heading", "text", "table", "image"])
        self.assertTrue(all(block["page_number"] == 3 for block in blocks))
        self.assertEqual(client.parsing.kwargs["expand"], ["markdown", "text", "items"])

    def test_api_key_is_required_without_an_injected_client(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pdf_path = Path(temporary) / "report.pdf"
            pdf_path.write_bytes(b"%PDF-1.7 test")
            with self.assertRaisesRegex(RuntimeError, "LLAMA_CLOUD_API_KEY"):
                extract_document(pdf_path, temporary, api_key="")


if __name__ == "__main__":
    unittest.main()
