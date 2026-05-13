"""
config.py
Central configuration for the insurance RAG engine.
All values read from environment variables with sensible defaults.
Never hardcode any of these values in any other module.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── Qdrant ──────────────────────────────────────────────────────────
    qdrant_host: str = Field(default="localhost", alias="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, alias="QDRANT_PORT")
    qdrant_grpc_port: int = Field(default=6334, alias="QDRANT_GRPC_PORT")
    collection_name: str = Field(default="insurance_policies", alias="COLLECTION_NAME")

    # ── Redis ────────────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")
    cache_ttl_seconds: int = Field(default=604800, alias="CACHE_TTL_SECONDS")   # 7 days
    cache_similarity_threshold: float = Field(default=0.25, alias="CACHE_SIMILARITY_THRESHOLD")
    cache_max_scan: int = Field(default=10000, alias="CACHE_MAX_SCAN")

    # ── Embedding model ──────────────────────────────────────────────────
    # Start with all-MiniLM-L6-v2 (384 dims) for development.
    # Switch to nvidia/NV-Embed-v2 (4096 dims) for production.
    # When switching: recreate the Qdrant collection and re-ingest all docs.
    embed_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        alias="EMBED_MODEL",
    )
    embed_dim: int = Field(default=384, alias="EMBED_DIM")
    embed_batch_size: int = Field(default=32, alias="EMBED_BATCH_SIZE")

    # ── LLM ─────────────────────────────────────────────────────────────
    # For local inference via Ollama / vLLM, set LLM_BASE_URL.
    # For NVIDIA NIM API, set LLM_API_KEY and LLM_BASE_URL to NIM endpoint.
    llm_model: str = Field(default="nvidia/nemotron-3-8b-chat-4k", alias="LLM_MODEL")
    llm_base_url: str = Field(default="http://localhost:11434/v1", alias="LLM_BASE_URL")
    llm_api_key: str = Field(default="not-required", alias="LLM_API_KEY")
    llm_temperature: float = Field(default=0.1, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=512, alias="LLM_MAX_TOKENS")
    llm_timeout_seconds: int = Field(default=15, alias="LLM_TIMEOUT_SECONDS")

    # ── Retrieval ────────────────────────────────────────────────────────
    top_k: int = Field(default=20, alias="TOP_K")             # chunks retrieved from Qdrant
    rerank_top_n: int = Field(default=5, alias="RERANK_TOP_N") # chunks passed to LLM after reranking
    score_threshold: float = Field(default=0.60, alias="SCORE_THRESHOLD")
    rerank_confidence_floor: float = Field(default=0.40, alias="RERANK_CONFIDENCE_FLOOR")
    context_max_tokens: int = Field(default=8000, alias="CONTEXT_MAX_TOKENS")

    # ── Reranker ─────────────────────────────────────────────────────────
    reranker_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        alias="RERANKER_MODEL",
    )
    # Switch to nvidia/nv-rerankqa-mistral-4b-v3 for production.

    # ── API ───────────────────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    ingest_api_key: str = Field(default="change-me-in-production", alias="INGEST_API_KEY")

    # ── Observability ────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_raw_queries: bool = Field(default=False, alias="LOG_RAW_QUERIES")  # NEVER true in prod

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        populate_by_name = True


# Single shared instance imported by all modules
settings = Settings()