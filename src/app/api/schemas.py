"""
src/app/api/schemas.py
─────────────────────────────────────────────────────────────────────────────
Pydantic request/response models for all RAG API endpoints.

Strict typing throughout — no raw dicts passed between layers.
The LLM person adds their response fields to ChatResponse when ready.
"""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# POST /chat  — request
# ─────────────────────────────────────────────────────────────────────────────

class ChatFilters(BaseModel):
    """Optional payload filters to narrow Qdrant search scope."""
    coverage_type: str | None = Field(
        default=None,
        description="Filter by coverage type: 'fire', 'flood', 'theft', 'earthquake'",
        examples=["fire"],
    )
    region: str | None = Field(
        default=None,
        description="Filter by region: 'tamil_nadu', 'maharashtra', 'all'",
        examples=["tamil_nadu"],
    )


class ChatRequest(BaseModel):
    """Incoming chat query from the user."""
    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="The user's insurance-related question",
        examples=["Does my policy cover roof damage from a storm?"],
    )
    filters: ChatFilters = Field(
        default_factory=ChatFilters,
        description="Optional filters to narrow search scope",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /chat  — response
# ─────────────────────────────────────────────────────────────────────────────

class SourceChunk(BaseModel):
    """A single source chunk returned alongside the answer."""
    chunk_id:      str
    policy_id:     str
    section_title: str
    doc_type:      str
    snippet:       str  = Field(description="First 200 chars of chunk text")
    score:         float
    cited:         bool = Field(description="True if the LLM cited this chunk")


class RAGResult(BaseModel):
    """
    The RAG pipeline result — everything up to and including the prompt.
    Returned to the LLM person's code as the handoff payload.
    The LLM person populates 'answer' and returns the full ChatResponse.
    """
    messages:   list[dict[str, Any]] = Field(
        description="OpenAI-format messages ready for LLM inference"
    )
    sources:    list[SourceChunk]
    cache_hit:  bool
    confidence: bool
    blocked:    bool
    block_reason: str | None = None
    latency: dict[str, int] = Field(
        description="Per-stage latency in milliseconds"
    )


class ChatResponse(BaseModel):
    """
    Final response returned to the user.

    Fields populated by YOU (RAG pipeline):
      sources, cache_hit, confidence, blocked, latency

    Fields populated by LLM PERSON:
      answer, flagged, failed
    """
    # ── RAG fields (your responsibility) ──────────────────────────────────────
    sources:     list[SourceChunk] = Field(default_factory=list)
    cache_hit:   bool = Field(description="True if answered from Redis cache")
    confidence:  bool = Field(description="True if retrieval was confident")
    blocked:     bool = Field(description="True if input guardrail blocked the query")
    latency:     dict[str, int] = Field(
        default_factory=dict,
        description="Per-stage latency in milliseconds",
    )

    # ── LLM fields (LLM person's responsibility) ──────────────────────────────
    # These have safe defaults so the endpoint works before LLM is integrated.
    answer:  str  = Field(
        default="LLM integration pending.",
        description="The generated answer — populated by LLM integration",
    )
    flagged: bool = Field(
        default=False,
        description="True if output guardrail triggered — set by LLM integration",
    )
    failed:  bool = Field(
        default=False,
        description="True if LLM call failed — set by LLM integration",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /ingest  — request / response
# ─────────────────────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    """Trigger document ingestion from the API."""
    folder:      str  = Field(
        default="src/app/rag/docs",
        description="Folder path to ingest (relative to project root)",
    )
    dry_run:     bool = Field(
        default=False,
        description="Validate documents without writing to Qdrant",
    )
    flush_cache: bool = Field(
        default=False,
        description="Flush Redis cache for updated policies after ingest",
    )


class IngestResponse(BaseModel):
    chunks_ingested: int
    files_processed: int
    dry_run:         bool
    errors:          list[str] = Field(default_factory=list)
    duration_seconds: float


# ─────────────────────────────────────────────────────────────────────────────
# GET /health  — response
# ─────────────────────────────────────────────────────────────────────────────

class ServiceHealth(BaseModel):
    status:  str           # "ok" | "error"
    detail:  str | None = None


class HealthResponse(BaseModel):
    status:     str  # "healthy" | "degraded" | "unhealthy"
    qdrant:     ServiceHealth
    redis:      ServiceHealth
    embedder:   ServiceHealth
    # LLM person adds their health check here:
    llm:        ServiceHealth = Field(
        default_factory=lambda: ServiceHealth(
            status="pending",
            detail="LLM integration not yet configured",
        )
    )
    version:    str = "0.1.0"