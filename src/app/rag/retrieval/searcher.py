"""
src/app/rag/retrieval/searcher.py
─────────────────────────────────────────────────────────────────────────────
Qdrant similarity search with payload filtering.
Updated for qdrant-client >= 1.9 — uses query_points() instead of search().
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Filter,
    FieldCondition,
    MatchValue,
    MatchAny,
)

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[4]
SRC  = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.config import settings


def _get_client() -> QdrantClient:
    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        timeout=10,
    )


def _build_filter(
    doc_type: str | None = None,
    coverage_type: str | None = None,
    region: str | None = None,
    tags: list[str] | None = None,
) -> Filter | None:
    """
    Build a Qdrant payload filter from optional parameters.
    Returns None if no filters are set (searches entire collection).
    """
    conditions = []

    if doc_type:
        conditions.append(
            FieldCondition(key="doc_type", match=MatchValue(value=doc_type))
        )
    if coverage_type:
        conditions.append(
            FieldCondition(key="coverage_type", match=MatchValue(value=coverage_type))
        )
    if region:
        # Match the exact region OR "all" — docs tagged "all" apply everywhere
        conditions.append(
            FieldCondition(key="region", match=MatchAny(any=[region, "all"]))
        )
    if tags:
        conditions.append(
            FieldCondition(key="tags", match=MatchAny(any=tags))
        )

    return Filter(must=conditions) if conditions else None


def _point_to_dict(point: Any) -> dict[str, Any]:
    """
    Convert a QueryResponse point to a plain dict.
    Works with both ScoredPoint and QueryResponse objects.
    """
    # query_points returns QueryResponse objects — payload is on .payload
    payload = getattr(point, "payload", None) or {}
    score   = getattr(point, "score", 0.0) or 0.0

    return {
        "chunk_id":      payload.get("chunk_id", ""),
        "text":          payload.get("text", ""),
        "section_title": payload.get("section_title", ""),
        "policy_id":     payload.get("policy_id", ""),
        "doc_type":      payload.get("doc_type", ""),
        "coverage_type": payload.get("coverage_type", ""),
        "region":        payload.get("region", ""),
        "tags":          payload.get("tags", []),
        "source_file":   payload.get("source_file", ""),
        "version":       payload.get("version", ""),
        "last_updated":  payload.get("last_updated", ""),
        "qdrant_score":  round(float(score), 4),
    }


def search(
    query_embedding: list[float],
    doc_type: str | None = None,
    coverage_type: str | None = None,
    region: str | None = None,
    tags: list[str] | None = None,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """
    Run a similarity search against Qdrant.

    Uses client.query_points() — the correct API for qdrant-client >= 1.9.
    (The old client.search() was removed in 1.9+)

    Returns a list of chunk dicts sorted by similarity score (highest first).
    """
    k = top_k or settings.top_k
    query_filter = _build_filter(doc_type, coverage_type, region, tags)
    client = _get_client()

    try:
        # query_points() is the new unified search API in qdrant-client >= 1.9
        response = client.query_points(
            collection_name=settings.collection_name,
            query=query_embedding,          # pass the vector directly
            query_filter=query_filter,
            limit=k,
            score_threshold=settings.score_threshold,
            with_payload=True,
            with_vectors=False,
        )

        # response.points is a list of ScoredPoint objects
        return [_point_to_dict(p) for p in response.points]

    except Exception as exc:
        print(f"[searcher] ERROR during Qdrant search — {exc}")
        return []


def search_multi_type(
    query_embedding: list[float],
    coverage_type: str | None = None,
    region: str | None = None,
) -> list[dict[str, Any]]:
    """
    Run two parallel searches — one for policy docs, one for FAQs — and merge.

    Prevents one doc_type from drowning out the other in results.
    Each type contributes at most TOP_K // 2 results.
    """
    half_k = max(settings.top_k // 2, 5)

    policy_results = search(
        query_embedding=query_embedding,
        doc_type="policy",
        coverage_type=coverage_type,
        region=region,
        top_k=half_k,
    )
    faq_results = search(
        query_embedding=query_embedding,
        doc_type="faq",
        coverage_type=coverage_type,
        region=region,
        top_k=half_k,
    )

    # Merge and de-duplicate by chunk_id, sort by score
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for chunk in policy_results + faq_results:
        cid = chunk.get("chunk_id", "")
        if cid not in seen:
            seen.add(cid)
            merged.append(chunk)

    merged.sort(key=lambda c: c.get("qdrant_score", 0), reverse=True)
    return merged


def qdrant_health() -> dict[str, Any]:
    """Check Qdrant connectivity. Used by the /health endpoint."""
    try:
        client = _get_client()
        info = client.get_collection(settings.collection_name)
        return {
            "status":        "ok",
            "collection":    settings.collection_name,
            "vectors_count": info.vectors_count,
            "points_count":  info.points_count,
        }
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}