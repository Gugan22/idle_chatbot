"""
config.py
─────────────────────────────────────────────────────────────────────────────
Central configuration for the insurance RAG engine.
All values are read from environment variables (via .env file).

Usage in any module:
    from config import settings
    print(settings.qdrant_host)

Never call os.getenv() directly anywhere else in the codebase.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8080, alias="PORT")
    env: str = Field(default="development", alias="ENV")
    # env controls: "development" shows /docs, "production" hides it

    # ── Auth (carried over from existing config) ──────────────────────────────
    auth_secret: str = Field(default="change-me", alias="AUTH_SECRET")
    token_ttl_seconds: int = Field(default=900000, alias="TOKEN_TTL_SECONDS")
    default_username: str = Field(default="admin", alias="DEFAULT_USERNAME")
    default_password: str = Field(default="admin", alias="DEFAULT_PASSWORD")

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_host: str = Field(default="localhost", alias="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, alias="QDRANT_PORT")
    qdrant_grpc_port: int = Field(default=6334, alias="QDRANT_GRPC_PORT")
    collection_name: str = Field(default="insurance_policies", alias="COLLECTION_NAME")

    # ── Redis semantic cache ──────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")
    cache_ttl_seconds: int = Field(default=604800, alias="CACHE_TTL_SECONDS")
    cache_similarity_threshold: float = Field(default=0.25, alias="CACHE_SIMILARITY_THRESHOLD")
    cache_max_scan: int = Field(default=10000, alias="CACHE_MAX_SCAN")

    # ── Embedding model ───────────────────────────────────────────────────────
    # Dev:  sentence-transformers/all-MiniLM-L6-v2  (384 dims, CPU-friendly)
    # Prod: nvidia/NV-Embed-v2                       (4096 dims, GPU)
    # Changing EMBED_DIM requires --recreate on the Qdrant collection + full re-ingest
    embed_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        alias="EMBED_MODEL",
    )
    embed_dim: int = Field(default=384, alias="EMBED_DIM")
    embed_batch_size: int = Field(default=32, alias="EMBED_BATCH_SIZE")
    embed_doc_prefix: str = Field(default="", alias="EMBED_DOC_PREFIX")
    embed_query_prefix: str = Field(default="", alias="EMBED_QUERY_PREFIX")

    # ── LLM ───────────────────────────────────────────────────────────────────
    # Works with any OpenAI-compatible endpoint:
    #   Ollama  → LLM_BASE_URL=http://localhost:11434/v1  LLM_API_KEY=not-required
    #   NIM     → LLM_BASE_URL=https://integrate.api.nvidia.com/v1  LLM_API_KEY=nvapi-...
    #   OpenAI  → LLM_BASE_URL=https://api.openai.com/v1  LLM_API_KEY=sk-...
    llm_model: str = Field(default="llama3", alias="LLM_MODEL")
    llm_base_url: str = Field(default="http://localhost:11434/v1", alias="LLM_BASE_URL")
    llm_api_key: str = Field(default="not-required", alias="LLM_API_KEY")
    llm_temperature: float = Field(default=0.1, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=512, alias="LLM_MAX_TOKENS")
    llm_timeout_seconds: int = Field(default=15, alias="LLM_TIMEOUT_SECONDS")

    # ── OpenAI key (for RAGAS evaluation or OpenAI LLM option) ───────────────
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    # ── Reranker ──────────────────────────────────────────────────────────────
    # Dev:  cross-encoder/ms-marco-MiniLM-L-6-v2   (CPU-friendly)
    # Prod: nvidia/nv-rerankqa-mistral-4b-v3
    reranker_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        alias="RERANKER_MODEL",
    )

    # ── Retrieval tuning ──────────────────────────────────────────────────────
    top_k: int = Field(default=20, alias="TOP_K")
    rerank_top_n: int = Field(default=5, alias="RERANK_TOP_N")
    score_threshold: float = Field(default=0.60, alias="SCORE_THRESHOLD")
    rerank_confidence_floor: float = Field(default=0.40, alias="RERANK_CONFIDENCE_FLOOR")
    context_max_tokens: int = Field(default=8000, alias="CONTEXT_MAX_TOKENS")

    # ── API security ──────────────────────────────────────────────────────────
    ingest_api_key: str = Field(default="change-me-in-production", alias="INGEST_API_KEY")

    # ── Observability ─────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_raw_queries: bool = Field(default=False, alias="LOG_RAW_QUERIES")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        populate_by_name = True


# Single shared instance — imported by every module
# Never instantiate Settings() more than once
settings = Settings()