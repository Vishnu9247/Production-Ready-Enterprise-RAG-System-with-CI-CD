"""Document storage provider construction."""

from ..core.config import Settings
from .azure_blob import AzureBlobDocumentStorage
from .base import DocumentStorage
from .local import LocalDocumentStorage


def create_document_storage(settings: Settings) -> DocumentStorage:
    if settings.object_storage_provider == "azure_blob":
        return AzureBlobDocumentStorage(settings)
    return LocalDocumentStorage(settings.data_directory / "originals")
