"""Agent that removes duplicate chunks and reranks the remaining evidence."""

import re

from ..core.config import Settings
from ..core.schemas import SearchResult
from ..embedding_generation.service import AzureOpenAIService
from .models import RerankResult
from .state import QueryWorkflowState


class ContextQualityAgent:
    def __init__(self, settings: Settings, azure: AzureOpenAIService) -> None:
        self.settings = settings
        self.azure = azure

    def deduplicate_and_rerank(self, state: QueryWorkflowState) -> dict:
        candidates = self._deduplicate(state.get("candidates", []))
        if not candidates:
            return {"context": []}

        blocks = "\n\n".join(
            f"CHUNK_ID: {candidate.chunk_id}\nCONTENT: {candidate.text}"
            for candidate in candidates[: self.settings.rerank_candidate_count]
        )
        result = self.azure.complete_structured(
            [
                {
                    "role": "system",
                    "content": (
                        "Rank the supplied chunks by how directly they help answer the query. "
                        "Return only supplied chunk IDs, most relevant first. Exclude unrelated "
                        "chunks. Do not answer the query."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Query:\n{state['resolved_query']}\n\nChunks:\n{blocks}",
                },
            ],
            RerankResult,
        )
        by_id = {candidate.chunk_id: candidate for candidate in candidates}
        ordered: list[SearchResult] = []
        seen: set[str] = set()
        for chunk_id in result.ranked_chunk_ids:
            if chunk_id in by_id and chunk_id not in seen:
                ordered.append(by_id[chunk_id])
                seen.add(chunk_id)
        for candidate in candidates:
            if candidate.chunk_id not in seen:
                ordered.append(candidate)
        limit = state.get("top_k") or self.settings.rerank_top_k
        return {"context": ordered[:limit]}

    @staticmethod
    def _deduplicate(candidates: list[SearchResult]) -> list[SearchResult]:
        unique: list[SearchResult] = []
        chunk_ids: set[str] = set()
        normalized_texts: set[str] = set()
        for candidate in candidates:
            normalized = re.sub(r"\s+", " ", candidate.text).strip().casefold()
            if candidate.chunk_id in chunk_ids or normalized in normalized_texts:
                continue
            chunk_ids.add(candidate.chunk_id)
            normalized_texts.add(normalized)
            unique.append(candidate)
        return unique
