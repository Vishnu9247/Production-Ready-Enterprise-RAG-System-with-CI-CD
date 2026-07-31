"""State shared by the LangGraph query agents."""

from typing import Any, Literal, TypedDict

from ..core.schemas import ConversationMessage, Reference, SearchResult


class QueryWorkflowState(TypedDict, total=False):
    session_id: str
    namespace: str
    query: str
    resolved_query: str
    search_mode: Literal["hybrid", "semantic", "keyword"]
    top_k: int | None
    metadata_filter: dict[str, Any] | None
    score_threshold: float | None
    is_complete: bool
    history_messages_needed: int
    history: list[ConversationMessage]
    candidates: list[SearchResult]
    context: list[SearchResult]
    answer: str
    reason: str
    references: list[Reference]
