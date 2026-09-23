"""Application settings — validated against environment variables at import time."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # App
    app_name: str = "Hybrid Retrieval RAG Service"
    app_version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"

    # Anthropic
    anthropic_api_key: str = Field(..., description="Anthropic API key — required")
    llm_model: str = "claude-sonnet-4-6"

    # Embeddings — hosted Cohere Embed API (embed-english-v3.0, 1024-dim).
    # Hosted (not a local model) so no PyTorch is loaded at startup — keeps the
    # process under Render's 512 MB free-tier limit.
    embedding_model: str = "embed-english-v3.0"
    embedding_dimensions: int = 1024

    # Tokenizer used ONLY to count tokens for chunk sizing. Kept local and
    # lightweight (a fast tokenizer, no PyTorch); the Cohere embedding model has
    # no public local tokenizer, so chunk sizing uses this as a stable proxy.
    chunk_tokenizer_model: str = "BAAI/bge-small-en-v1.5"

    # Retrieval
    retrieval_top_k: int = Field(default=10, ge=1, le=50)
    rerank_top_k: int = Field(default=3, ge=1, le=20)

    # Cohere — required: powers both embeddings (embed-english-v3.0) and reranking
    cohere_api_key: str = Field(
        ..., description="Cohere API key — required (embeddings + reranking)"
    )

    # Pinecone
    pinecone_api_key: str = Field(..., description="Pinecone API key — required")
    # 1024-dim serverless index matching embed-english-v3.0; created on first run if absent.
    pinecone_index_name: str = "hybrid-retrieval-rag"

    # Chunking — token-based sizes, not character-based
    chunk_size: int = Field(default=512, ge=64, le=2048)
    chunk_overlap: int = Field(default=64, ge=0, le=256)

    # Generation
    max_tokens: int = Field(default=1024, ge=64, le=4096)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)


settings = Settings()
