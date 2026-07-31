"""Structured responses returned by individual LLM-backed agents."""

from pydantic import BaseModel, Field


class QueryAnalysis(BaseModel):
    is_complete: bool
    history_messages_needed: int = Field(ge=0)
    explanation: str = Field(
        description="A short operational explanation, not hidden chain-of-thought."
    )


class RewrittenQuery(BaseModel):
    query: str = Field(min_length=1)


class RerankResult(BaseModel):
    ranked_chunk_ids: list[str] = Field(default_factory=list)


class GroundedAnswerDraft(BaseModel):
    answer: str
    reason: str = Field(
        description="A concise evidence summary explaining which supplied facts support the answer."
    )
    cited_reference_numbers: list[int] = Field(default_factory=list)
