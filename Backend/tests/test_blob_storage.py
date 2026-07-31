import tempfile
import unittest
from pathlib import Path

from Backend.rag_app.core.config import Settings
from Backend.rag_app.document_storage.azure_blob import AzureBlobDocumentStorage


class FakeBlobClient:
    url = "https://account.blob.core.windows.net/rag-documents/documents/doc_1/report.pdf"

    def upload_blob(self, source, **kwargs):
        self.content = source.read()
        self.kwargs = kwargs


class FakeContainerClient:
    def get_blob_client(self, blob_name):
        self.blob_name = blob_name
        self.blob = FakeBlobClient()
        return self.blob


class FakeBlobServiceClient:
    def get_container_client(self, container):
        self.container = container
        self.container_client = FakeContainerClient()
        return self.container_client


class AzureBlobStorageTests(unittest.TestCase):
    def test_pdf_is_uploaded_to_deterministic_blob_name(self) -> None:
        client = FakeBlobServiceClient()
        settings = Settings(
            _env_file=None,
            object_storage_provider="azure_blob",
            azure_storage_account_url="https://account.blob.core.windows.net",
            azure_storage_container="rag-documents",
            azure_storage_prefix="documents",
        )
        storage = AzureBlobDocumentStorage(settings, service_client=client)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.pdf"
            path.write_bytes(b"%PDF-test")
            uri = storage.upload_pdf(path, "doc_1", "../report.pdf")

        self.assertEqual(client.container, "rag-documents")
        self.assertEqual(
            client.container_client.blob_name, "documents/doc_1/report.pdf"
        )
        self.assertEqual(client.container_client.blob.content, b"%PDF-test")
        self.assertEqual(uri, FakeBlobClient.url)


if __name__ == "__main__":
    unittest.main()
