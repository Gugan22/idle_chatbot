from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import uvicorn

from app import settings
from app.api import auth_router, rag_router, health_router
from app.security import JWTAuthMiddleware


def create_app() -> JWTAuthMiddleware:
    app = FastAPI(
        title="Insurance RAG Chatbot API",
        description="Auto and homeowners insurance assistant powered by RAG",
        version="0.1.0",
        docs_url="/docs" if settings.env == "development" else None,
        redoc_url=None,
    )

    # Akilu changed this because users need a browser interface for asking
    # questions without manually calling the protected API endpoints.
    frontend_dir = Path(__file__).resolve().parent / "frontend"
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def frontend_redirect() -> RedirectResponse:
        return RedirectResponse(url="/chat")

    @app.get("/chat", include_in_schema=False)
    async def chatbot_frontend():
        from fastapi.responses import FileResponse
        return FileResponse(frontend_dir / "index.html")

    app.include_router(auth_router)
    app.include_router(rag_router,    prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")

    app = JWTAuthMiddleware(app)
    return app


app = create_app()


def start_server() -> None:
    """Start the configured HTTP server from any working directory."""
    uvicorn.run(
        "app.main:app",
        app_dir=str(Path(__file__).resolve().parents[1]),
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        from app.rag.ingestion.embedder import embed_query
        from app.rag.retrieval import search_multi_type, rerank, is_confident, build_prompt, build_no_context_response

        query = "Does my fire policy cover the attached garage?"
        print(f"\n[test] Query: {query}")
        embedding = embed_query(query)
        print(f"[test] Embedded — {len(embedding)} dims")
        chunks = search_multi_type(embedding, coverage_type="fire")
        print(f"[test] Retrieved {len(chunks)} chunks from Qdrant")
        if not chunks:
            print("[test] No chunks — run 'make ingest' first.")
            sys.exit(0)
        ranked = rerank(query, chunks)
        if not ranked:
            print("[test] Reranker returned nothing.")
            sys.exit(0)
        top = ranked[0]
        print(f"[test] Top chunk: '{top.get('section_title')}' score={top.get('rerank_score')}")
        if is_confident(ranked):
            prompt = build_prompt(query, ranked)
            print(f"[test] Prompt ready — ~{prompt['estimated_tokens']} tokens")
            print("[test] Phase 3 + 4 RAG pipeline working end to end.")
        else:
            print(build_no_context_response())
        sys.exit(0)

    start_server()
