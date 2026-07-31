"""Local document storage used for development and tests."""

import shutil
from pathlib import Path


class LocalDocumentStorage:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def upload_pdf(self, file_path: Path, document_id: str, document_name: str) -> str:
        target_directory = self.directory / document_id
        target_directory.mkdir(parents=True, exist_ok=True)
        target = target_directory / Path(document_name).name
        shutil.copy2(file_path, target)
        return target.resolve().as_uri()
