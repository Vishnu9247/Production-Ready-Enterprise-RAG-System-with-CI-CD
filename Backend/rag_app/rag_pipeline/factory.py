"""Cached construction of application services."""

from functools import lru_cache

from ..core.config import get_settings
from .service import RAGService


@lru_cache
def get_rag_service() -> RAGService:
    """Return a single configured RAG service for the application process."""
    return RAGService(get_settings())
