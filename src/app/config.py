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

import os
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_project_root() -> Path:
    """Use the source checkout root, or the launch directory for installed packages."""
    source_root = Path(__file__).resolve().parents[2]
    if (source_root / "pyproject.toml").is_file():
        return source_root
    return Path.cwd().resolve()


PROJECT_ROOT = _resolve_project_root()
ENV_FILE = Path(os.getenv("ENV_FILE", PROJECT_ROOT / ".env")).expanduser().resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8080, alias="PORT")
    env: str = Field(default="development", alias="ENV")
    # env controls: "development" shows /docs, "production" hides it

    # ── Auth (carried over from existing config) ──────────────────────────────
    auth_secret: str = Field(default="", alias="AUTH_SECRET")
    token_ttl_seconds: int = Field(default=3600, alias="TOKEN_TTL_SECONDS")
    default_username: str = Field(default="", alias="DEFAULT_USERNAME")
    default_password: str = Field(default="", alias="DEFAULT_PASSWORD")

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_host: str = Field(default="localhost", alias="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, alias="QDRANT_PORT")
    qdrant_grpc_port: int = Field(default=6334, alias="QDRANT_GRPC_PORT")
    collection_name: str = Field(default="insurance_policies", alias="COLLECTION_NAME")
    docs_dir: Path = Field(default=PROJECT_ROOT / "src/app/rag/docs", alias="DOCS_DIR")

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
    embed_local_files_only: bool = Field(default=False, alias="EMBED_LOCAL_FILES_ONLY")

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
    ingest_api_key: str = Field(default="", alias="INGEST_API_KEY")

    # ── Observability ─────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_raw_queries: bool = Field(default=False, alias="LOG_RAW_QUERIES")

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Reject known development credentials before a production server starts."""
        if self.env.lower() != "production":
            return self

        unsafe = {
            "AUTH_SECRET": {"", "change-me", "replace-with-a-long-random-secret"},
            "DEFAULT_USERNAME": {"", "admin", "replace-with-a-username"},
            "DEFAULT_PASSWORD": {"", "admin", "replace-with-a-strong-password"},
            "INGEST_API_KEY": {"", "change-me-in-production", "dev-ingest-key-change-in-prod",
                               "replace-with-a-long-random-ingest-key"},
        }
        values = {
            "AUTH_SECRET": self.auth_secret,
            "DEFAULT_USERNAME": self.default_username,
            "DEFAULT_PASSWORD": self.default_password,
            "INGEST_API_KEY": self.ingest_api_key,
        }
        invalid = [name for name, value in values.items() if value in unsafe[name]]
        if len(self.auth_secret) < 32:
            invalid.append("AUTH_SECRET (minimum 32 characters)")
        if len(self.default_password) < 12:
            invalid.append("DEFAULT_PASSWORD (minimum 12 characters)")
        if len(self.ingest_api_key) < 32:
            invalid.append("INGEST_API_KEY (minimum 32 characters)")
        if invalid:
            raise ValueError(
                "Production configuration contains unsafe defaults: "
                + ", ".join(dict.fromkeys(invalid))
            )
        return self


# Single shared instance — imported by every module
# Never instantiate Settings() more than once
settings = Settings()
