"""Production container process entry point."""

import os

import uvicorn

from .core.config import get_settings
from .database.repository import PostgresDocumentRepository


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    """Initialize required storage and start the ASGI server."""
    settings = get_settings()
    if _enabled(os.getenv("AUTO_INIT_DB", "true")):
        PostgresDocumentRepository(settings).initialize_schema()

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "Backend.rag_app.api:app",
        host="0.0.0.0",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
