"""Document storage interface."""

from pathlib import Path
from typing import Protocol


class DocumentStorage(Protocol):
    def upload_pdf(self, file_path: Path, document_id: str, document_name: str) -> str:
        """Upload a PDF and return its durable storage URI."""
        ...
