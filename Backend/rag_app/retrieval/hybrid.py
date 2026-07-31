"""Hybrid retrieval using Pinecone and PostgreSQL reciprocal-rank fusion."""

from typing import Literal

from ..core.config import Settings
from ..core.schemas import SearchResult
from ..database.repository import PostgresDocumentRepository
from ..vector_store_operations.pinecone_store import PineconeVectorStore


SearchMode = Literal["hybrid", "semantic", "keyword"]


class HybridRetriever:
    def __init__(
        self,
        settings: Settings,
        vector_store: PineconeVectorStore,
        document_repository: PostgresDocumentRepository | None = None,
    ) -> None:
        self.settings = settings
        self.vector_store = vector_store
        self.document_repository = document_repository

    def search(
        self,
        query_text: str,
        *,
        mode: SearchMode = "hybrid",
        top_k: int | None = None,
        namespace: str | None = None,
        metadata_filter: dict | None = None,
        score_threshold: float | None = None,
    ) -> list[SearchResult]:
        limit = top_k or self.settings.retrieval_top_k
        target_namespace = namespace or self.settings.pinecone_namespace
        if mode == "semantic":
            return self.vector_store.query(
                query_text,
                top_k=limit,
                namespace=target_namespace,
                metadata_filter=metadata_filter,
                score_threshold=score_threshold,
            )
        if self.document_repository is None:
            if mode == "keyword":
                raise RuntimeError("PostgreSQL is required for keyword search")
            return self.vector_store.query(
                query_text,
                top_k=limit,
                namespace=target_namespace,
                metadata_filter=metadata_filter,
                score_threshold=score_threshold,
            )

        document_id = self._document_id_filter(metadata_filter)
        keyword_results = self.document_repository.keyword_search(
            query_text,
            namespace=target_namespace,
            top_k=max(limit, self.settings.keyword_search_top_k),
            document_id=document_id,
        )
        if mode == "keyword":
            return keyword_results[:limit]

        semantic_results = self.vector_store.query(
            query_text,
            top_k=max(limit, self.settings.semantic_search_top_k),
            namespace=target_namespace,
            metadata_filter=metadata_filter,
            score_threshold=score_threshold,
        )
        return self._reciprocal_rank_fusion(
            semantic_results, keyword_results, limit, target_namespace
        )

    def _reciprocal_rank_fusion(
        self,
        semantic_results: list[SearchResult],
        keyword_results: list[SearchResult],
        top_k: int,
        namespace: str,
    ) -> list[SearchResult]:
        scores: dict[str, float] = {}
        candidates: dict[str, SearchResult] = {}
        semantic_scores: dict[str, float] = {}
        keyword_scores: dict[str, float] = {}
        rrf_k = self.settings.hybrid_rrf_k

        for rank, result in enumerate(semantic_results, start=1):
            scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + 1.0 / (rrf_k + rank)
            candidates[result.chunk_id] = result
            semantic_scores[result.chunk_id] = result.score
        for rank, result in enumerate(keyword_results, start=1):
            scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + 1.0 / (rrf_k + rank)
            candidates.setdefault(result.chunk_id, result)
            keyword_scores[result.chunk_id] = result.score

        ordered_ids = sorted(scores, key=scores.get, reverse=True)
        authoritative = self.document_repository.get_chunks(
            ordered_ids, namespace=namespace
        )
        maximum = max(scores.values(), default=1.0)
        fused: list[SearchResult] = []
        for chunk_id in ordered_ids[:top_k]:
            source = authoritative.get(chunk_id, candidates[chunk_id])
            metadata = dict(source.metadata) | {
                "retrieval_method": "hybrid",
                "semantic_score": semantic_scores.get(chunk_id, 0.0),
                "keyword_score": keyword_scores.get(chunk_id, 0.0),
            }
            fused.append(
                SearchResult(
                    chunk_id=chunk_id,
                    score=scores[chunk_id] / maximum,
                    text=source.text,
                    metadata=metadata,
                )
            )
        return fused

    @staticmethod
    def _document_id_filter(metadata_filter: dict | None) -> str | None:
        if not metadata_filter:
            return None
        value = metadata_filter.get("document_id")
        if isinstance(value, str):
            return value
        if isinstance(value, dict) and isinstance(value.get("$eq"), str):
            return value["$eq"]
        return None
