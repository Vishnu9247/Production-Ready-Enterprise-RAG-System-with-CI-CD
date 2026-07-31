"""Azure Blob Storage implementation for original PDFs."""

from pathlib import Path
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

from ..core.config import Settings


class AzureBlobDocumentStorage:
    def __init__(self, settings: Settings, service_client: Any | None = None) -> None:
        settings.require_blob_storage()
        self.settings = settings
        self.service_client = service_client or self._create_client(settings)
        self.container_client = self.service_client.get_container_client(
            settings.azure_storage_container
        )

    @staticmethod
    def _create_client(settings: Settings) -> BlobServiceClient:
        connection_string = settings.azure_storage_connection_string.get_secret_value().strip()
        if connection_string:
            return BlobServiceClient.from_connection_string(connection_string)

        credential = (
            settings.azure_storage_account_key.get_secret_value().strip()
            or settings.azure_storage_sas_token.get_secret_value().strip()
            or DefaultAzureCredential()
        )
        return BlobServiceClient(
            account_url=settings.azure_storage_account_url.rstrip("/"),
            credential=credential,
        )

    def upload_pdf(self, file_path: Path, document_id: str, document_name: str) -> str:
        safe_name = Path(document_name).name
        prefix = self.settings.azure_storage_prefix.strip("/")
        blob_name = "/".join(part for part in (prefix, document_id, safe_name) if part)
        blob_client = self.container_client.get_blob_client(blob_name)
        with file_path.open("rb") as source:
            blob_client.upload_blob(
                source,
                overwrite=True,
                content_settings=ContentSettings(content_type="application/pdf"),
            )
        return str(blob_client.url)
