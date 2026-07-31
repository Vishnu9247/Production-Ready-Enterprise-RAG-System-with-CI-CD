"""Shared domain and API models."""

from datetime import datetime
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


class Reference(BaseModel):
    number: int
    chunk_id: str
    document_id: str = ""
    document_name: str = ""
    page_numbers: list[int] = Field(default_factory=list)
    score: float
    storage_uri: str = ""


class Answer(BaseModel):
    session_id: str
    query: str
    resolved_query: str
    answer: str
    reason: str
    references: list[Reference] = Field(default_factory=list)


class QueryRequest(BaseModel):
    session_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=100)
    metadata_filter: dict[str, Any] | None = None
    score_threshold: float | None = Field(default=None, ge=-1, le=1)
    search_mode: Literal["hybrid", "semantic", "keyword"] = "hybrid"


class SessionCreateRequest(BaseModel):
    name: str = Field(default="New research session", min_length=1, max_length=200)
    namespace: str = Field(default="default", min_length=1, max_length=128)


class SessionResponse(BaseModel):
    session_id: str
    name: str
    namespace: str
    created_at: datetime
    updated_at: datetime


class ConversationMessage(BaseModel):
    message_id: str
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    resolved_query: str | None = None
    reason: str | None = None
    references: list[Reference] = Field(default_factory=list)
    created_at: datetime


class SessionHistoryResponse(BaseModel):
    session: SessionResponse
    messages: list[ConversationMessage] = Field(default_factory=list)


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
