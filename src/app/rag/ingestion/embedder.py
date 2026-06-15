"""
src/app/rag/ingestion/embedder.py
─────────────────────────────────────────────────────────────────────────────
Singleton embedding wrapper.
Fixed: get_sentence_embedding_dimension() → get_embedding_dimension()
"""

from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
SRC  = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.config import settings

DOCUMENT_PREFIX = settings.embed_doc_prefix
QUERY_PREFIX = settings.embed_query_prefix


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """Load the embedding model once and cache it for the process lifetime."""
    print(f"[embedder] Loading model '{settings.embed_model}'...")
    # Akilu changed this because local development must be able to load a
    # cached embedding model when Hugging Face network access is unavailable.
    model = SentenceTransformer(
        settings.embed_model,
        local_files_only=settings.embed_local_files_only,
    )

    # get_embedding_dimension() is the current API (get_sentence_embedding_dimension
    # is deprecated in sentence-transformers >= 3.x)
    actual_dim = model.get_embedding_dimension()
    print(f"[embedder] Model loaded. Embedding dimension: {actual_dim}")

    if actual_dim != settings.embed_dim:
        raise ValueError(
            f"[embedder] Dimension mismatch: config says {settings.embed_dim} "
            f"but model produces {actual_dim}. Update EMBED_DIM in your .env."
        )

    return model


def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of document chunks.
    Used during ingestion only — NOT at query time.
    """
    if not texts:
        return []

    model = _get_model()
    prefixed = [f"{DOCUMENT_PREFIX}{t}" for t in texts] if DOCUMENT_PREFIX else texts

    embeddings = model.encode(
        prefixed,
        batch_size=settings.embed_batch_size,
        show_progress_bar=len(texts) > 100,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return [emb.tolist() for emb in embeddings]


def embed_query(text: str) -> list[float]:
    """
    Embed a single user query.
    Used at query time only — NOT during ingestion.
    Uses QUERY_PREFIX (different from document prefix for asymmetric models).
    """
    if not text or not text.strip():
        raise ValueError("[embedder] Cannot embed an empty query.")

    model = _get_model()
    prefixed = f"{QUERY_PREFIX}{text.strip()}" if QUERY_PREFIX else text.strip()

    embedding = model.encode(
        prefixed,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return embedding.tolist()


def get_embedding_dim() -> int:
    """Return the embedding dimension of the loaded model."""
    return _get_model().get_embedding_dimension()
