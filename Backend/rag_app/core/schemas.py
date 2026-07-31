"""Shared domain and API models."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    chunk_id: str
    text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    chunk_id: str
    score: float
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    number: int
    chunk_id: str
    document_id: str = ""
    document_name: str = ""
    page_numbers: list[int] = Field(default_factory=list)
    score: float


class Answer(BaseModel):
    answer: str
    citations: list[Citation]
    sources: list[SearchResult]


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=100)
    namespace: str | None = None
    metadata_filter: dict[str, Any] | None = None
    score_threshold: float | None = Field(default=None, ge=-1, le=1)
    search_mode: Literal["hybrid", "semantic", "keyword"] = "hybrid"


class KeywordSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=100)
    namespace: str | None = None
    document_id: str | None = None


class IngestResponse(BaseModel):
    document_id: str
    document_name: str
    chunks_upserted: int
    namespace: str
    storage_uri: str | None = None
