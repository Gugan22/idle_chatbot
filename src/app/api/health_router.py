"""
src/app/api/health_router.py
─────────────────────────────────────────────────────────────────────────────
GET /health — checks all services and returns their status.

Checks Qdrant, Redis, embedder, and LLM connectivity.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter

ROOT = Path(__file__).resolve().parents[4]
SRC  = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.api.schemas import HealthResponse, ServiceHealth
from app.rag.retrieval.searcher import qdrant_health
from app.rag.retrieval.cache import cache_stats

health_router = APIRouter(tags=["Health"])


@health_router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
)
async def health() -> HealthResponse:

    # ── Qdrant ────────────────────────────────────────────────────────────────
    q = qdrant_health()
    qdrant = ServiceHealth(
        status=q["status"],
        detail=(
            f"{q.get('points_count', 0)} points in collection"
            if q["status"] == "ok"
            else q.get("detail")
        ),
    )

    # ── Redis ─────────────────────────────────────────────────────────────────
    r = cache_stats()
    redis = ServiceHealth(
        status=r["status"],
        detail=(
            f"{r.get('total_entries', 0)} cached entries"
            if r["status"] == "ok"
            else r.get("detail")
        ),
    )

    # ── Embedder ──────────────────────────────────────────────────────────────
    try:
        from app.rag.ingestion.embedder import get_embedding_dim
        dim = get_embedding_dim()
        embedder = ServiceHealth(status="ok", detail=f"dim={dim}")
    except Exception as exc:
        embedder = ServiceHealth(status="error", detail=str(exc))

    # Akilu changed this because the health endpoint should expose whether the
    # configured chatbot provider is reachable before users send questions.
    from app.rag.generation.llm import llm_health
    lh = llm_health()
    llm = ServiceHealth(
        status=lh["status"],
        detail=lh.get("model") if lh["status"] == "ok" else lh.get("detail"),
    )

    # ── Overall status ────────────────────────────────────────────────────────
    critical = [qdrant.status, redis.status, embedder.status, llm.status]
    if all(s == "ok" for s in critical):
        overall = "healthy"
    elif any(s == "error" for s in critical):
        overall = "unhealthy"
    else:
        overall = "degraded"

    return HealthResponse(
        status=overall,
        qdrant=qdrant,
        redis=redis,
        embedder=embedder,
        llm=llm,
    )
