"""
src/app/rag/retrieval/reranker.py
─────────────────────────────────────────────────────────────────────────────
Cross-encoder reranker — second pass scoring after Qdrant retrieval.

Why reranking matters:
  Qdrant retrieves by vector proximity — chunks that are close in embedding
  space to the query. This is fast but approximate. A chunk about "fire
  damage coverage overview" and a chunk about "fire damage to attached
  garages specifically" may have very similar embeddings, but only the
  second actually answers "is my garage covered?".

  The reranker reads the query AND the chunk together as a pair and scores
  their relevance — much more accurate than embedding similarity alone.
  It takes the top-K from Qdrant (~20 chunks) and returns only the
  top-N most relevant (~5 chunks) to send to the LLM.

  For insurance use cases, this is non-negotiable. A wrong clause
  (e.g. flood exclusion instead of fire coverage) produces a confidently
  wrong answer that could mislead a real policyholder.

Dev model:  cross-encoder/ms-marco-MiniLM-L-6-v2  (CPU, fast, ~80MB)
Prod model: nvidia/nv-rerankqa-mistral-4b-v3       (GPU, best quality)

Singleton pattern: model loads once per process via _get_model().
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from sentence_transformers import CrossEncoder

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[4]
SRC  = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.config import settings


@lru_cache(maxsize=1)
def _get_model() -> CrossEncoder:
    """
    Load the cross-encoder reranker model once and cache it.
    Subsequent calls return the same instance — no double loading.
    """
    print(f"[reranker] Loading model '{settings.reranker_model}'...")
    model = CrossEncoder(
        settings.reranker_model,
        max_length=512,    # truncate long chunks to fit model context
    )
    print("[reranker] Model loaded.")
    return model


def rerank(
    query: str,
    chunks: list[dict[str, Any]],
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    """
    Rerank a list of retrieved chunks by relevance to the query.

    Args:
        query:   the original user query string (NOT the embedding)
        chunks:  list of chunk dicts from searcher.search() or search_multi_type()
        top_n:   number of chunks to return after reranking
                 (default: settings.rerank_top_n)

    Returns:
        Top-N chunks sorted by rerank_score descending.
        Each chunk dict gets two new fields added:
          - rerank_score  : float — cross-encoder relevance score (higher = better)
          - rerank_rank   : int   — rank position (1 = best)

    If chunks list is empty or model fails, returns the original list
    truncated to top_n (graceful fallback to Qdrant scores).
    """
    n = top_n or settings.rerank_top_n

    if not chunks:
        return []

    # If fewer chunks than top_n, return all of them (no reranking needed)
    if len(chunks) <= n:
        for i, chunk in enumerate(chunks):
            chunk["rerank_score"] = chunk.get("qdrant_score", 0.0)
            chunk["rerank_rank"]  = i + 1
        return chunks

    try:
        model = _get_model()

        # Build (query, chunk_text) pairs for the cross-encoder
        # The model reads both together and scores their relevance
        pairs = [(query, chunk.get("text", "")) for chunk in chunks]

        # Predict relevance scores — returns a list of floats
        scores: list[float] = model.predict(pairs).tolist()

        # Attach scores to chunks
        for chunk, score in zip(chunks, scores):
            chunk["rerank_score"] = round(float(score), 4)

        # Sort by rerank_score descending
        ranked = sorted(chunks, key=lambda c: c["rerank_score"], reverse=True)

        # Assign rank positions and slice to top_n
        top = ranked[:n]
        for i, chunk in enumerate(top):
            chunk["rerank_rank"] = i + 1

        return top

    except Exception as exc:
        print(f"[reranker] WARNING: Reranking failed — {exc}. Falling back to Qdrant scores.")
        # Graceful fallback: return top-N by Qdrant score
        fallback = sorted(chunks, key=lambda c: c.get("qdrant_score", 0), reverse=True)[:n]
        for i, chunk in enumerate(fallback):
            chunk["rerank_score"] = chunk.get("qdrant_score", 0.0)
            chunk["rerank_rank"]  = i + 1
        return fallback


def is_confident(chunks: list[dict[str, Any]]) -> bool:
    """
    Check whether the top reranked chunk meets the confidence floor.

    If the best chunk's rerank_score is below RERANK_CONFIDENCE_FLOOR,
    the system has no confident answer and should return a fallback
    message rather than hallucinating from weak context.

    Call this AFTER rerank() and BEFORE building the prompt.

    Returns:
        True  → confident enough to send to LLM
        False → return "I don't have that information" to the user
    """
    if not chunks:
        return False
    top_score = chunks[0].get("rerank_score", 0.0)
    return top_score >= settings.rerank_confidence_floor