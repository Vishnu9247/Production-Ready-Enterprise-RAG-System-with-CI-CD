"""Pinecone index lifecycle and vector operations."""

from collections.abc import Iterable
from typing import Any

from pinecone import Pinecone, ServerlessSpec

from ..core.config import Settings
from ..core.schemas import Chunk, SearchResult
from ..embedding_generation.service import AzureOpenAIService


def _metadata_value(value: Any) -> str | float | bool | list[str] | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        cleaned = [str(item) for item in value if item is not None]
        return cleaned or None
    return str(value)


def prepare_metadata(chunk: Chunk) -> dict[str, Any]:
    metadata = {
        key: clean
        for key, value in chunk.metadata.items()
        if (clean := _metadata_value(value)) is not None
    }
    metadata["text"] = chunk.text
    return metadata


class PineconeVectorStore:
    def __init__(
        self,
        settings: Settings,
        embeddings: AzureOpenAIService,
        client: Pinecone | None = None,
    ) -> None:
        self.settings = settings
        self.embeddings = embeddings
        if client is None:
            settings.require_pinecone()
            client = Pinecone(api_key=settings.pinecone_api_key.get_secret_value())
        self.client = client

    def ensure_index(self) -> Any:
        host = self.settings.pinecone_host.strip()
        if host:
            return self.client.index(host=host)

        name = self.settings.pinecone_index_name
        if not self.client.has_index(name):
            self.client.create_index(
                name=name,
                dimension=self.settings.embedding_dimensions,
                metric=self.settings.pinecone_metric,
                spec=ServerlessSpec(
                    cloud=self.settings.pinecone_cloud,
                    region=self.settings.pinecone_region,
                ),
            )
        description = self.client.describe_index(name)
        dimension = getattr(description, "dimension", None)
        if dimension is not None and dimension != self.settings.embedding_dimensions:
            raise RuntimeError(
                f"Pinecone index dimension is {dimension}, but embeddings use "
                f"{self.settings.embedding_dimensions}. Use a matching index or setting."
            )
        return self.client.index(name=name)

    def upsert_chunks(
        self,
        chunks: Iterable[Chunk],
        *,
        namespace: str | None = None,
        batch_size: int = 100,
    ) -> int:
        items = list(chunks)
        if not items:
            return 0
        index = self.ensure_index()
        vectors = self.embeddings.embed_documents(chunk.text for chunk in items)
        target_namespace = namespace or self.settings.pinecone_namespace
        for start in range(0, len(items), batch_size):
            batch_chunks = items[start : start + batch_size]
            batch_vectors = vectors[start : start + batch_size]
            index.upsert(
                vectors=[
                    {
                        "id": chunk.chunk_id,
                        "values": vector,
                        "metadata": prepare_metadata(chunk),
                    }
                    for chunk, vector in zip(batch_chunks, batch_vectors, strict=True)
                ],
                namespace=target_namespace,
            )
        return len(items)

    def query(
        self,
        query_text: str,
        *,
        top_k: int | None = None,
        namespace: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[SearchResult]:
        response = self.ensure_index().query(
            vector=self.embeddings.embed_query(query_text),
            namespace=namespace or self.settings.pinecone_namespace,
            top_k=top_k or self.settings.retrieval_top_k,
            include_metadata=True,
            include_values=False,
            filter=metadata_filter,
        )
        threshold = score_threshold if score_threshold is not None else self.settings.retrieval_score_threshold
        results: list[SearchResult] = []
        for match in response.matches:
            metadata = dict(match.metadata or {})
            text = str(metadata.pop("text", ""))
            score = float(match.score)
            if threshold is None or score >= threshold:
                results.append(
                    SearchResult(chunk_id=str(match.id), score=score, text=text, metadata=metadata)
                )
        return results

    def update_metadata(
        self, vector_id: str, metadata: dict[str, Any], *, namespace: str | None = None
    ) -> Any:
        clean = {
            key: value
            for key, raw in metadata.items()
            if (value := _metadata_value(raw)) is not None
        }
        return self.ensure_index().update(
            id=vector_id,
            set_metadata=clean,
            namespace=namespace or self.settings.pinecone_namespace,
        )

    def update_values(
        self, vector_id: str, values: list[float], *, namespace: str | None = None
    ) -> Any:
        if len(values) != self.settings.embedding_dimensions:
            raise ValueError(
                f"Expected {self.settings.embedding_dimensions} embedding values, got {len(values)}"
            )
        return self.ensure_index().update(
            id=vector_id,
            values=values,
            namespace=namespace or self.settings.pinecone_namespace,
        )

    def replace_chunk(self, chunk: Chunk, *, namespace: str | None = None) -> Any:
        values = self.embeddings.embed_query(chunk.text)
        return self.ensure_index().upsert(
            vectors=[
                {"id": chunk.chunk_id, "values": values, "metadata": prepare_metadata(chunk)}
            ],
            namespace=namespace or self.settings.pinecone_namespace,
        )

    def delete_document(self, document_id: str, *, namespace: str | None = None) -> Any:
        return self.ensure_index().delete(
            filter={"document_id": {"$eq": document_id}},
            namespace=namespace or self.settings.pinecone_namespace,
        )

    def delete_vectors(self, vector_ids: list[str], *, namespace: str | None = None) -> Any:
        return self.ensure_index().delete(
            ids=vector_ids, namespace=namespace or self.settings.pinecone_namespace
        )

    def delete_namespace(self, *, namespace: str | None = None) -> Any:
        return self.ensure_index().delete(
            delete_all=True, namespace=namespace or self.settings.pinecone_namespace
        )
