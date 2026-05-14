"""
ingestion/embedder.py
────────────────────────────────────────────────────────────────────────────
Singleton wrapper around the sentence-transformers embedding model.

Two distinct functions:
  - embed_batch()  : for ingestion — embeds document chunks in batches
  - embed_query()  : for query time — embeds a user question

Why two functions?
  Nemotron Embed VL (and other asymmetric retrieval models) use different
  instruction prefixes for documents vs queries to maximise recall.
  Mixing them degrades retrieval quality significantly.

  For all-MiniLM-L6-v2 (symmetric model used in dev), the prefixes are
  empty strings so both functions behave identically — safe to use either.

  When you upgrade to nvidia/NV-Embed-v2 (production), the prefixes become:
    document prefix: "passage: "
    query prefix:    "query: "
  The DOCUMENT_PREFIX / QUERY_PREFIX constants below handle this.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING

from sentence_transformers import SentenceTransformer

from app import settings

if TYPE_CHECKING:
    pass

# ── Instruction prefixes ───────────────────────────────────────────────────
# For all-MiniLM-L6-v2: both are empty (symmetric model)
# For NV-Embed-v2:       document="passage: " query="query: "
# For e5-mistral:        document="passage: " query="Instruct: ...\nQuery: "
# Override via env vars without changing code.

DOCUMENT_PREFIX = os.getenv("EMBED_DOC_PREFIX", "")
QUERY_PREFIX    = os.getenv("EMBED_QUERY_PREFIX", "")


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """
    Load the embedding model once and cache it.
    lru_cache(maxsize=1) ensures a single instance per process regardless
    of how many modules import this function.
    """
    print(f"[embedder] Loading model '{settings.embed_model}'...")
    model = SentenceTransformer(settings.embed_model)
    print(f"[embedder] Model loaded. Embedding dimension: {model.get_sentence_embedding_dimension()}")

    # Sanity check: confirm the model dimension matches config
    actual_dim = model.get_sentence_embedding_dimension()
    if actual_dim != settings.embed_dim:
        raise ValueError(
            f"[embedder] Model dimension mismatch: "
            f"config says {settings.embed_dim} but model produces {actual_dim}. "
            f"Update EMBED_DIM in your .env file."
        )

    return model


def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of document chunks.
    Used during ingestion only.

    Prepends DOCUMENT_PREFIX to each text before encoding.
    Processes in batches of EMBED_BATCH_SIZE for throughput efficiency.

    Returns a list of float lists (one embedding per input text).
    """
    if not texts:
        return []

    model = _get_model()

    # Prepend document prefix if set
    prefixed = [f"{DOCUMENT_PREFIX}{t}" for t in texts] if DOCUMENT_PREFIX else texts

    embeddings = model.encode(
        prefixed,
        batch_size=settings.embed_batch_size,
        show_progress_bar=len(texts) > 100,
        normalize_embeddings=True,   # cosine similarity works best with normalised vectors
        convert_to_numpy=True,
    )

    return [emb.tolist() for emb in embeddings]


def embed_query(text: str) -> list[float]:
    """
    Embed a single user query.
    Used during retrieval only — NOT during ingestion.

    Prepends QUERY_PREFIX before encoding.
    Returns a single float list.
    """
    if not text or not text.strip():
        raise ValueError("[embedder] Cannot embed empty query.")

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
    return _get_model().get_sentence_embedding_dimension()