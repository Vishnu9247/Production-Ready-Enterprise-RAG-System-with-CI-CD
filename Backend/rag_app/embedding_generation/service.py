"""Azure OpenAI embedding and chat client wrappers."""

from collections.abc import Iterable
from typing import Any, TypeVar

from openai import AzureOpenAI
from pydantic import BaseModel

from ..core.config import Settings


StructuredResponse = TypeVar("StructuredResponse", bound=BaseModel)


class AzureOpenAIService:
    def __init__(self, settings: Settings, client: AzureOpenAI | None = None) -> None:
        self.settings = settings
        if client is None:
            settings.require_azure()
            client = AzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint.rstrip("/"),
                api_key=settings.azure_openai_api_key.get_secret_value(),
                api_version=settings.azure_openai_api_version,
            )
        self.client = client

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        items = list(texts)
        if not items:
            return []
        if any(not text.strip() for text in items):
            raise ValueError("Embedding inputs must not be empty")
        embeddings: list[list[float]] = []
        batch_size = self.settings.embedding_batch_size
        for start in range(0, len(items), batch_size):
            response = self.client.embeddings.create(
                model=self.settings.azure_openai_embedding_deployment,
                input=items[start : start + batch_size],
                dimensions=self.settings.embedding_dimensions,
            )
            embeddings.extend(item.embedding for item in sorted(response.data, key=lambda x: x.index))
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def complete(self, messages: list[dict[str, str]], *, temperature: float = 0.0) -> str:
        response: Any = self.client.chat.completions.create(
            model=self.settings.azure_openai_chat_deployment,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    def complete_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[StructuredResponse],
        *,
        temperature: float = 0.0,
    ) -> StructuredResponse:
        response: Any = self.client.beta.chat.completions.parse(
            model=self.settings.azure_openai_chat_deployment,
            messages=messages,
            response_format=response_model,
            temperature=temperature,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError("Azure OpenAI did not return the requested structured response")
        return parsed
