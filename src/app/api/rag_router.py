"""
src/app/api/rag_router.py
─────────────────────────────────────────────────────────────────────────────
RAG API routes — POST /chat and POST /ingest.

Your responsibility:
  - Running the full RAG pipeline up to prompt-ready
  - Returning RAGResult with messages, sources, cache_hit, confidence
  - The /ingest endpoint

LLM person's responsibility:
  - Replacing the LLM_STUB block in /chat with their generate() call
  - Populating answer, flagged, failed in ChatResponse
  - The streaming /chat/stream endpoint (optional)

Handoff is clearly marked with:
  # ── LLM INTEGRATION POINT ──
"""

from __future__ import annotations

import time
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.responses import StreamingResponse

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[4]
SRC  = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.config import settings
from app.api.schemas import (
    ChatRequest, ChatResponse, ChatFilters,
    RAGResult, SourceChunk,
    IngestRequest, IngestResponse,
)
from app.rag.ingestion.embedder import embed_query
from app.rag.retrieval import (
    check_cache,
    store_in_cache,
    search_multi_type,
    rerank,
    is_confident,
    build_prompt,
    build_no_context_response,
    extract_cited_chunks,
)
from app.rag.generation.guardrails import run_input_guard

rag_router = APIRouter(prefix="/rag", tags=["RAG"])


# ── Auth dependency ───────────────────────────────────────────────────────────
# /ingest is protected — only callers with the correct API key can trigger it
def verify_ingest_key(x_ingest_key: str = Header(...)) -> None:
    if x_ingest_key != settings.ingest_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid ingest API key.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/rag/chat
# ─────────────────────────────────────────────────────────────────────────────

@rag_router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask an insurance question",
    description=(
        "Runs the full RAG pipeline: guardrail → embed → cache → search → "
        "rerank → prompt. The LLM call is handled separately."
    ),
)
async def chat(request: ChatRequest) -> ChatResponse:
    t_start = time.perf_counter()
    latency: dict[str, int] = {}

    # ── Step 1: Input guardrail ───────────────────────────────────────────────
    guard = run_input_guard(request.query)
    if guard["blocked"]:
        return ChatResponse(
            answer=guard["message"],
            sources=[],
            cache_hit=False,
            confidence=False,
            blocked=True,
            latency={"total_ms": _ms(t_start)},
        )

    # ── Step 2: Embed query ───────────────────────────────────────────────────
    t0 = time.perf_counter()
    try:
        query_embedding = embed_query(request.query)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Embedding failed: {exc}",
        )
    latency["embed_ms"] = _ms(t0)

    # ── Step 3: Redis cache check ─────────────────────────────────────────────
    t0 = time.perf_counter()
    cached = check_cache(query_embedding)
    latency["cache_ms"] = _ms(t0)

    if cached:
        latency["total_ms"] = _ms(t_start)
        return ChatResponse(
            answer=cached["answer"],
            sources=_ids_to_sources(cached.get("chunk_ids", [])),
            cache_hit=True,
            confidence=True,
            blocked=False,
            latency=latency,
        )

    # ── Step 4: Qdrant search ─────────────────────────────────────────────────
    t0 = time.perf_counter()
    chunks = search_multi_type(
        query_embedding=query_embedding,
        coverage_type=request.filters.coverage_type,
        region=request.filters.region,
    )
    latency["search_ms"] = _ms(t0)

    # ── Step 5: Rerank ────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    ranked_chunks = rerank(request.query, chunks)
    latency["rerank_ms"] = _ms(t0)

    # ── Step 6: Confidence check ──────────────────────────────────────────────
    if not is_confident(ranked_chunks):
        latency["total_ms"] = _ms(t_start)
        return ChatResponse(
            answer=build_no_context_response(),
            sources=[],
            cache_hit=False,
            confidence=False,
            blocked=False,
            latency=latency,
        )

    # ── Step 7: Build prompt ──────────────────────────────────────────────────
    prompt_result = build_prompt(request.query, ranked_chunks)
    messages      = prompt_result["messages"]
    used_chunks   = prompt_result["context_chunks"]
    sources       = _chunks_to_sources(used_chunks, "")

    latency["total_ms"] = _ms(t_start)

    # ─────────────────────────────────────────────────────────────────────────
    # ── LLM INTEGRATION POINT ────────────────────────────────────────────────
    # Everything above this line is the RAG pipeline (Gugan's work).
    # Everything below this line is LLM integration (other person's work).
    #
    # The LLM person should:
    #   1. Import their generate() function
    #   2. Call it with `messages`
    #   3. Run output guardrail on the answer
    #   4. Call store_in_cache() with the final answer
    #   5. Populate answer, flagged, failed in ChatResponse
    #
    # Example:
    #   from app.rag.generation.llm import generate
    #   from app.rag.generation.guardrails import check_output
    #
    #   llm_result     = generate(messages)
    #   output_check   = check_output(llm_result["answer"], used_chunks)
    #   final_answer   = output_check["answer"]
    #   cited_ids      = extract_cited_chunks(final_answer, used_chunks)
    #   store_in_cache(request.query, query_embedding, final_answer, cited_ids)
    #
    #   return ChatResponse(
    #       answer   = final_answer,
    #       sources  = _chunks_to_sources(used_chunks, final_answer),
    #       cache_hit  = False,
    #       confidence = True,
    #       blocked    = False,
    #       flagged    = output_check["flagged"],
    #       failed     = llm_result["failed"],
    #       latency    = latency,
    #   )
    # ─────────────────────────────────────────────────────────────────────────

    # Temporary stub response — returns the RAG result without LLM answer
    # Remove this block once LLM integration is complete
    return ChatResponse(
        answer="[LLM integration pending — RAG pipeline returned successfully]",
        sources=sources,
        cache_hit=False,
        confidence=True,
        blocked=False,
        latency=latency,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/rag/context
# Returns the RAG result (prompt + sources) without calling the LLM.
# Useful for the LLM person to test their integration independently.
# ─────────────────────────────────────────────────────────────────────────────

@rag_router.post(
    "/context",
    response_model=RAGResult,
    summary="Get RAG context without LLM (for LLM integration testing)",
    description=(
        "Returns the full RAG pipeline result — messages, sources, confidence — "
        "without calling the LLM. The LLM person uses this to test their integration."
    ),
)
async def get_context(request: ChatRequest) -> RAGResult:
    t_start = time.perf_counter()
    latency: dict[str, int] = {}

    guard = run_input_guard(request.query)
    if guard["blocked"]:
        return RAGResult(
            messages=[],
            sources=[],
            cache_hit=False,
            confidence=False,
            blocked=True,
            block_reason=guard["reason"],
            latency={"total_ms": _ms(t_start)},
        )

    t0 = time.perf_counter()
    query_embedding = embed_query(request.query)
    latency["embed_ms"] = _ms(t0)

    t0 = time.perf_counter()
    cached = check_cache(query_embedding)
    latency["cache_ms"] = _ms(t0)

    if cached:
        return RAGResult(
            messages=[{"role": "assistant", "content": cached["answer"]}],
            sources=_ids_to_sources(cached.get("chunk_ids", [])),
            cache_hit=True,
            confidence=True,
            blocked=False,
            latency={"total_ms": _ms(t_start), **latency},
        )

    t0 = time.perf_counter()
    chunks = search_multi_type(
        query_embedding=query_embedding,
        coverage_type=request.filters.coverage_type,
        region=request.filters.region,
    )
    latency["search_ms"] = _ms(t0)

    t0 = time.perf_counter()
    ranked_chunks = rerank(request.query, chunks)
    latency["rerank_ms"] = _ms(t0)

    if not is_confident(ranked_chunks):
        return RAGResult(
            messages=[],
            sources=[],
            cache_hit=False,
            confidence=False,
            blocked=False,
            latency={"total_ms": _ms(t_start), **latency},
        )

    prompt_result = build_prompt(request.query, ranked_chunks)
    latency["total_ms"] = _ms(t_start)

    return RAGResult(
        messages=prompt_result["messages"],
        sources=_chunks_to_sources(prompt_result["context_chunks"], ""),
        cache_hit=False,
        confidence=True,
        blocked=False,
        latency=latency,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/rag/ingest
# ─────────────────────────────────────────────────────────────────────────────

@rag_router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Ingest documents into Qdrant",
    description="Parses .md files and loads them into Qdrant. Protected by X-Ingest-Key header.",
    dependencies=[Depends(verify_ingest_key)],
)
async def ingest(request: IngestRequest) -> IngestResponse:
    import time as _time
    from pathlib import Path as _Path
    from app.rag.ingestion.parser import parse_folder, parse_file, ParseError
    from app.rag.ingestion.qdrant_writer import upsert_chunks
    from app.rag.retrieval.cache import invalidate_by_policy

    t_start = _time.perf_counter()
    errors: list[str] = []
    total_chunks = 0
    files_processed = 0

    folder = _Path(request.folder)
    if not folder.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Folder not found: {request.folder}",
        )

    all_chunks = []
    md_files = sorted(folder.rglob("*.md"))

    for file_path in md_files:
        try:
            chunks = parse_file(file_path)
            all_chunks.extend(chunks)
            files_processed += 1
        except ParseError as exc:
            errors.append(str(exc))

    if not request.dry_run and all_chunks:
        upserted = upsert_chunks(all_chunks, dry_run=False)
        total_chunks = upserted

        if request.flush_cache:
            policy_ids = {c.get("policy_id") for c in all_chunks if c.get("policy_id")}
            for pid in policy_ids:
                invalidate_by_policy(pid)
    else:
        total_chunks = len(all_chunks)

    return IngestResponse(
        chunks_ingested=total_chunks,
        files_processed=files_processed,
        dry_run=request.dry_run,
        errors=errors,
        duration_seconds=round(_time.perf_counter() - t_start, 2),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ms(since: float) -> int:
    return int((time.perf_counter() - since) * 1000)


def _chunks_to_sources(
    chunks: list[dict],
    answer: str,
) -> list[SourceChunk]:
    cited = set(extract_cited_chunks(answer, chunks)) if answer else set()
    return [
        SourceChunk(
            chunk_id      = c.get("chunk_id", ""),
            policy_id     = c.get("policy_id", ""),
            section_title = c.get("section_title", ""),
            doc_type      = c.get("doc_type", ""),
            snippet       = c.get("text", "")[:200],
            score         = c.get("rerank_score", 0.0),
            cited         = c.get("chunk_id", "") in cited,
        )
        for c in chunks
    ]


def _ids_to_sources(chunk_ids: list[str]) -> list[SourceChunk]:
    return [
        SourceChunk(
            chunk_id="", policy_id="", section_title="",
            doc_type="", snippet="", score=0.0, cited=True,
        )
        for _ in chunk_ids
    ]