"""Environment-based application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=(".env", "Backend/.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Enterprise RAG API"
    environment: str = "development"
    data_directory: Path = Path("Backend/data")

    azure_openai_endpoint: str = ""
    azure_openai_api_key: SecretStr = Field(default=SecretStr(""))
    azure_openai_api_version: str = "2024-02-01"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    azure_openai_chat_deployment: str = "gpt-4o-mini"
    embedding_dimensions: int = Field(default=1536, gt=0)
    embedding_batch_size: int = Field(default=64, ge=1, le=2048)

    pinecone_api_key: SecretStr = Field(default=SecretStr(""))
    pinecone_host: str = ""
    pinecone_index_name: str = "enterprise-rag"
    pinecone_namespace: str = "default"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    pinecone_metric: str = "cosine"

    postgres_host: str = ""
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_database: str = "rag_db"
    postgres_user: str = ""
    postgres_password: SecretStr = Field(default=SecretStr(""))
    postgres_sslmode: str = "require"
    postgres_pool_size: int = Field(default=5, ge=1)
    postgres_max_overflow: int = Field(default=10, ge=0)

    object_storage_provider: Literal["local", "azure_blob"] = "local"
    azure_storage_account_url: str = ""
    azure_storage_container: str = ""
    azure_storage_prefix: str = "documents"
    azure_storage_connection_string: SecretStr = Field(default=SecretStr(""))
    azure_storage_account_key: SecretStr = Field(default=SecretStr(""))
    azure_storage_sas_token: SecretStr = Field(default=SecretStr(""))

    chunk_size: int = Field(default=1800, ge=200)
    chunk_overlap: int = Field(default=200, ge=0)
    retrieval_top_k: int = Field(default=5, ge=1, le=100)
    retrieval_score_threshold: float | None = Field(default=None, ge=-1, le=1)
    keyword_search_top_k: int = Field(default=20, ge=1, le=100)
    semantic_search_top_k: int = Field(default=20, ge=1, le=100)
    hybrid_rrf_k: int = Field(default=60, ge=1)

    def require_azure(self) -> None:
        missing = []
        if not self.azure_openai_endpoint.strip():
            missing.append("AZURE_OPENAI_ENDPOINT")
        if not self.azure_openai_api_key.get_secret_value().strip():
            missing.append("AZURE_OPENAI_API_KEY")
        if missing:
            raise RuntimeError(f"Missing required Azure OpenAI settings: {', '.join(missing)}")

    def require_pinecone(self) -> None:
        if not self.pinecone_api_key.get_secret_value().strip():
            raise RuntimeError("Missing required Pinecone setting: PINECONE_API_KEY")

    @property
    def database_configured(self) -> bool:
        return all(
            (
                self.postgres_host.strip(),
                self.postgres_database.strip(),
                self.postgres_user.strip(),
                self.postgres_password.get_secret_value().strip(),
            )
        )

    def require_database(self) -> None:
        missing = []
        if not self.postgres_host.strip():
            missing.append("POSTGRES_HOST")
        if not self.postgres_database.strip():
            missing.append("POSTGRES_DATABASE")
        if not self.postgres_user.strip():
            missing.append("POSTGRES_USER")
        if not self.postgres_password.get_secret_value().strip():
            missing.append("POSTGRES_PASSWORD")
        if missing:
            raise RuntimeError(f"Missing required PostgreSQL settings: {', '.join(missing)}")

    def require_blob_storage(self) -> None:
        if self.object_storage_provider != "azure_blob":
            return
        missing = []
        if not self.azure_storage_container.strip():
            missing.append("AZURE_STORAGE_CONTAINER")
        has_connection_string = bool(
            self.azure_storage_connection_string.get_secret_value().strip()
        )
        if not has_connection_string and not self.azure_storage_account_url.strip():
            missing.append("AZURE_STORAGE_ACCOUNT_URL")
        if missing:
            raise RuntimeError(
                f"Missing required Azure Blob Storage settings: {', '.join(missing)}"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
