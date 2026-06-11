from fastapi import FastAPI
from dotenv import load_dotenv
import uvicorn

load_dotenv()

from app import settings
from app.api import auth_router, rag_router, health_router
from app.security import JWTAuthMiddleware


def create_app() -> JWTAuthMiddleware:
    app = FastAPI(
        title="Insurance RAG Chatbot API",
        description="Home insurance assistant powered by RAG",
        version="0.1.0",
        docs_url="/docs" if settings.env == "development" else None,
        redoc_url=None,
    )

    app.include_router(auth_router)
    app.include_router(rag_router,    prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")

    app = JWTAuthMiddleware(app)
    return app


app = create_app()


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

    host = settings.host
    port = settings.port
    try:
        uvicorn.run("app.main:app", app_dir="src", host=host, port=port, reload=True)
    except OSError as e:
        msg = str(e)
        if "10013" in msg or getattr(e, "winerror", None) == 10013:
            print(f"\nERROR: Could not bind to {host}:{port}")
            for p in range(port + 1, port + 11):
                try:
                    uvicorn.run("app.main:app", app_dir="src", host=host, port=p, reload=True)
                    break
                except OSError:
                    continue
        else:
            print("uvicorn failed to start:", e)