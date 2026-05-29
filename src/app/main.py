from fastapi import FastAPI
from dotenv import load_dotenv
import uvicorn

# Load .env BEFORE importing config so pydantic-settings picks up all values
load_dotenv()

# ── Settings ───────────────────────────────────────────────────────────────────
from app import settings

# ── Routers ────────────────────────────────────────────────────────────────────
from app.api import auth_router

# ── Middleware ─────────────────────────────────────────────────────────────────
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

    # Uncomment as each phase is completed:
    # from app.api.rag_router import rag_router
    # from app.api.health_router import health_router
    # app.include_router(rag_router, prefix="/api/v1")
    # app.include_router(health_router, prefix="/api/v1")

    app = JWTAuthMiddleware(app)
    return app


app = create_app()


def start_server():
    host = settings.host
    port = settings.port

    try:
        uvicorn.run("app.main:app", app_dir="src", host=host, port=port, reload=True)

    except OSError as e:
        msg = str(e)
        if "10013" in msg or getattr(e, "winerror", None) == 10013:
            print()
            print(f"ERROR: Could not bind to {host}:{port} — permission denied or port in use.")
            print("Attempting to find an alternate port...")
            tried = []
            success = False
            for p in range(port + 1, port + 11):
                try:
                    print(f"Trying port {p}...")
                    uvicorn.run("app.main:app", app_dir="src", host=host, port=p, reload=True)
                    success = True
                    break
                except OSError as e2:
                    tried.append((p, str(e2)))
            if not success:
                print("\nCould not bind to any alternative ports.")
                for p, m in tried:
                    print(f"  - {p}: {m}")
                print(f"\n  Workaround: set PORT=8081 && poetry run python src/app/main.py")
        else:
            print("uvicorn failed to start:", e)


if __name__ == "__main__":
    start_server()
