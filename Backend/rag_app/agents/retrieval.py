"""Agent that performs semantic, keyword, or hybrid document retrieval."""

from ..core.config import Settings
from ..retrieval.hybrid import HybridRetriever
from .state import QueryWorkflowState


class RetrievalAgent:
    def __init__(self, settings: Settings, retriever: HybridRetriever) -> None:
        self.settings = settings
        self.retriever = retriever

    def retrieve(self, state: QueryWorkflowState) -> dict:
        requested = state.get("top_k") or self.settings.rerank_top_k
        candidate_count = max(requested, self.settings.rerank_candidate_count)
        candidates = self.retriever.search(
            state["resolved_query"],
            mode=state["search_mode"],
            top_k=candidate_count,
            namespace=state["namespace"],
            metadata_filter=state.get("metadata_filter"),
            score_threshold=state.get("score_threshold"),
        )
        return {"candidates": candidates}
