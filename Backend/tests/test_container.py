"""Tests for the production container launcher."""

import os
import unittest
from unittest.mock import MagicMock, patch

from Backend.rag_app import container


class ContainerLauncherTests(unittest.TestCase):
    @patch("Backend.rag_app.container.uvicorn.run")
    @patch("Backend.rag_app.container.PostgresDocumentRepository")
    @patch("Backend.rag_app.container.get_settings")
    def test_initializes_database_and_starts_uvicorn(
        self,
        get_settings: MagicMock,
        repository: MagicMock,
        uvicorn_run: MagicMock,
    ) -> None:
        settings = get_settings.return_value
        with patch.dict(os.environ, {"PORT": "9000", "AUTO_INIT_DB": "true"}):
            container.main()

        repository.assert_called_once_with(settings)
        repository.return_value.initialize_schema.assert_called_once_with()
        uvicorn_run.assert_called_once_with(
            "Backend.rag_app.api:app",
            host="0.0.0.0",
            port=9000,
            proxy_headers=True,
            forwarded_allow_ips="*",
        )

    @patch("Backend.rag_app.container.uvicorn.run")
    @patch("Backend.rag_app.container.PostgresDocumentRepository")
    def test_database_initialization_can_be_disabled(
        self, repository: MagicMock, uvicorn_run: MagicMock
    ) -> None:
        with patch.dict(os.environ, {"AUTO_INIT_DB": "false"}, clear=False):
            container.main()

        repository.assert_not_called()
        uvicorn_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
