"""
src/app/rag/retrieval/__init__.py
─────────────────────────────────────────────────────────────────────────────
Public API for the retrieval package.

Import from here in the pipeline:
    from app.rag.retrieval import check_cache, store_in_cache
    from app.rag.retrieval import search, search_multi_type
    from app.rag.retrieval import rerank, is_confident
    from app.rag.retrieval import build_prompt, build_no_context_response
"""

from app.rag.retrieval.cache import (
    check_cache,
    store_in_cache,
    invalidate_by_policy,
    flush_all_cache,
    cache_stats,
)

from app.rag.retrieval.searcher import (
    search,
    search_multi_type,
    qdrant_health,
)

from app.rag.retrieval.reranker import (
    rerank,
    is_confident,
)

from app.rag.retrieval.prompt_builder import (
    build_prompt,
    build_no_context_response,
    extract_cited_chunks,
)

__all__ = [
    "check_cache", "store_in_cache", "invalidate_by_policy",
    "flush_all_cache", "cache_stats",
    "search", "search_multi_type", "qdrant_health",
    "rerank", "is_confident",
    "build_prompt", "build_no_context_response", "extract_cited_chunks",
]