"""
src/app/rag/retrieval/cache.py
─────────────────────────────────────────────────────────────────────────────
Redis semantic cache for the insurance RAG chatbot.

How it works:
  1. User sends a query
  2. Query is embedded into a vector
  3. We scan Redis for a cached entry whose embedding is close enough
     (cosine distance < threshold) to the current query
  4. HIT  → return the cached answer instantly (no Qdrant, no LLM)
  5. MISS → run full RAG pipeline, then store the answer in Redis

Why this matters:
  Insurance users ask the same 20-30 questions repeatedly.
  "Does fire cover my garage?" and "Is the attached garage covered under fire?"
  are different strings but the same question. Semantic cache catches both
  from a single stored entry — bypassing Qdrant and LLM entirely.

Cache invalidation:
  When a policy is updated and re-ingested, call invalidate_by_policy()
  to flush all cached answers that reference chunks from that policy.
  This is wired into the ingest pipeline automatically.
"""

from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path
from typing import Any

import numpy as np
import redis

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[4]
SRC  = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.config import settings

# ── Redis key prefix ──────────────────────────────────────────────────────────
# All cache entries are stored under "rag:faq:{hash}"
# This makes it easy to scan, inspect, and flush cache entries.
KEY_PREFIX = "rag:faq:"


def _get_client() -> redis.Redis:
    """
    Create a Redis client from the REDIS_URL in settings.
    Uses hiredis parser for faster serialisation when available.
    """
    return redis.from_url(
        settings.redis_url,
        decode_responses=False,   # we store raw bytes (JSON-encoded)
        socket_connect_timeout=5,
        socket_timeout=5,
    )


def _cosine_distance(a: list[float], b: list[float]) -> float:
    """
    Compute cosine distance between two vectors.
    Returns 0.0 for identical vectors, 1.0 for orthogonal.
    Lower = more similar.
    """
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return float(1.0 - np.dot(va, vb) / (norm_a * norm_b))


def _make_key(query: str) -> str:
    """
    Generate a stable Redis key from a query string.
    Uses SHA-256 so the key is always the same length regardless of query length.
    """
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    return f"{KEY_PREFIX}{digest}"


def check_cache(query_embedding: list[float]) -> dict[str, Any] | None:
    """
    Scan Redis for a semantically similar cached answer.

    Args:
        query_embedding: the embedded vector of the user's query

    Returns:
        dict with keys {"answer", "chunk_ids", "query"} if cache HIT
        None if cache MISS

    Note:
        This uses a linear scan — fine under ~10K cached entries.
        At 50K+ entries, switch to a RedisSearch vector index (see README).
    """
    try:
        client = _get_client()
        threshold = settings.cache_similarity_threshold
        scanned = 0

        for key in client.scan_iter(match=f"{KEY_PREFIX}*", count=100):
            if scanned >= settings.cache_max_scan:
                break
            scanned += 1

            raw = client.get(key)
            if not raw:
                continue

            try:
                entry: dict = json.loads(raw)
            except json.JSONDecodeError:
                continue

            cached_embedding = entry.get("embedding")
            if not cached_embedding:
                continue

            dist = _cosine_distance(query_embedding, cached_embedding)
            if dist < threshold:
                # Cache HIT — refresh TTL so hot entries stay alive longer
                client.expire(key, settings.cache_ttl_seconds)
                return {
                    "answer":    entry.get("answer", ""),
                    "chunk_ids": entry.get("chunk_ids", []),
                    "query":     entry.get("query", ""),
                    "distance":  dist,
                }

        return None   # cache MISS

    except redis.RedisError as exc:
        # Never let cache errors break the main pipeline
        print(f"[cache] WARNING: Redis error during cache check — {exc}")
        return None


def store_in_cache(
    query: str,
    query_embedding: list[float],
    answer: str,
    chunk_ids: list[str] | None = None,
) -> bool:
    """
    Store a question-answer pair in Redis with TTL.

    Args:
        query:           the original user query text (stored for debugging)
        query_embedding: the embedded vector of the query
        answer:          the LLM-generated answer
        chunk_ids:       list of chunk_ids that contributed to the answer
                         (used for invalidation when a policy is updated)

    Returns:
        True if stored successfully, False if Redis is unavailable.
    """
    try:
        client = _get_client()
        key = _make_key(query)

        payload = json.dumps({
            "query":     query,
            "embedding": query_embedding,
            "answer":    answer,
            "chunk_ids": chunk_ids or [],
        })

        client.setex(
            name=key,
            time=settings.cache_ttl_seconds,
            value=payload.encode("utf-8"),
        )
        return True

    except redis.RedisError as exc:
        print(f"[cache] WARNING: Failed to store in cache — {exc}")
        return False


def invalidate_by_policy(policy_id: str) -> int:
    """
    Delete all cached answers that reference chunks from a given policy_id.

    Call this automatically after re-ingesting a policy document so users
    never receive stale cached answers after a policy update.

    Args:
        policy_id: e.g. "HOME-FIRE-TN-2024"

    Returns:
        Number of cache entries deleted.
    """
    try:
        client = _get_client()
        deleted = 0

        for key in client.scan_iter(match=f"{KEY_PREFIX}*", count=100):
            raw = client.get(key)
            if not raw:
                continue
            try:
                entry: dict = json.loads(raw)
            except json.JSONDecodeError:
                continue

            # Check if any of the chunk_ids in this entry belong to the policy
            chunk_ids: list[str] = entry.get("chunk_ids", [])
            if any(policy_id.lower() in cid.lower() for cid in chunk_ids):
                client.delete(key)
                deleted += 1

        print(f"[cache] Invalidated {deleted} cache entries for policy_id='{policy_id}'.")
        return deleted

    except redis.RedisError as exc:
        print(f"[cache] WARNING: Failed to invalidate cache — {exc}")
        return 0


def flush_all_cache() -> int:
    """
    Delete ALL cache entries. Use only in development or during a full re-ingest.

    Returns:
        Number of keys deleted.
    """
    try:
        client = _get_client()
        keys = list(client.scan_iter(match=f"{KEY_PREFIX}*"))
        if keys:
            client.delete(*keys)
        print(f"[cache] Flushed {len(keys)} cache entries.")
        return len(keys)
    except redis.RedisError as exc:
        print(f"[cache] WARNING: Failed to flush cache — {exc}")
        return 0


def cache_stats() -> dict[str, Any]:
    """
    Return basic cache statistics for the health endpoint.
    """
    try:
        client = _get_client()
        keys = list(client.scan_iter(match=f"{KEY_PREFIX}*"))
        client.ping()
        return {
            "status":      "ok",
            "total_entries": len(keys),
            "ttl_seconds": settings.cache_ttl_seconds,
            "threshold":   settings.cache_similarity_threshold,
        }
    except redis.RedisError as exc:
        return {"status": "error", "detail": str(exc)}