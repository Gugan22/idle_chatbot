# =============================================================================
# Makefile — Insurance RAG Chatbot
# Works on Windows (PowerShell / Git Bash) and Mac.
#
# Commands:
#   make setup        First-time: install deps + start infra + create collection
#   make dev          DEV : Qdrant + Redis in Podman, app via Poetry (hot-reload)
#   make qa           QA  : fully containerised with .env.qa
#   make prod         PROD: fully containerised with .env.prod
#   make stop-dev     Stop dev containers
#   make stop-qa      Stop QA containers
#   make stop-prod    Stop prod containers
#   make ingest       Ingest all docs from src/app/rag/docs/
#   make ingest-dry   Validate docs without writing to Qdrant
#   make logs-qa      Tail QA container logs
#   make logs-prod    Tail prod container logs
#   make test         Run pytest
#   make clean        Remove containers (volumes preserved)
# =============================================================================

# ── OS detection — blank line echo differs between Windows and Mac/Linux ──────
ifeq ($(OS),Windows_NT)
  BLANK = @echo.
else
  BLANK = @echo ""
endif

COMPOSE = podman-compose -f docker/podman-compose.yml

.PHONY: dev qa prod stop-dev stop-qa stop-prod setup \
        ingest ingest-dry logs-qa logs-prod test clean help

.DEFAULT_GOAL := help

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	$(BLANK)
	@echo   Insurance RAG Chatbot - available commands
	$(BLANK)
	@echo   make setup        First-time: install deps + start infra + create collection
	@echo   make dev          DEV : Qdrant + Redis in Podman, app via Poetry hot-reload
	@echo   make qa           QA  : fully containerised with .env.qa
	@echo   make prod         PROD: fully containerised with .env.prod
	$(BLANK)
	@echo   make stop-dev     Stop dev containers
	@echo   make stop-qa      Stop QA containers
	@echo   make stop-prod    Stop prod containers
	$(BLANK)
	@echo   make ingest       Ingest all docs from src/app/rag/docs/
	@echo   make ingest-dry   Validate docs without writing to Qdrant
	@echo   make logs-qa      Tail QA container logs
	@echo   make logs-prod    Tail prod container logs
	@echo   make test         Run pytest
	@echo   make clean        Remove containers (volumes preserved)
	$(BLANK)

# ── First-time setup ──────────────────────────────────────────────────────────
setup:
	@echo [setup] Installing Python dependencies...
	poetry install
	@echo [setup] Starting Podman machine...
	-podman machine start
	@echo [setup] Starting Qdrant and Redis...
	$(COMPOSE) --profile dev up qdrant redis -d
	@echo [setup] Waiting 15s for services to be healthy...
	poetry run python -c "import time; time.sleep(15)"
	@echo [setup] Creating Qdrant collection...
	poetry run python src/app/rag/setup.py
	$(BLANK)
	@echo [setup] Done. Next steps:
	@echo   1. Add your .md files to src/app/rag/docs/
	@echo   2. make ingest-dry
	@echo   3. make ingest
	@echo   4. make dev
	$(BLANK)

# ── DEV — infrastructure in Podman, FastAPI via Poetry ───────────────────────
dev:
	-podman machine start
	@echo [dev] Starting Qdrant + Redis...
	$(COMPOSE) --profile dev up qdrant redis -d
	@echo [dev] Waiting 10s for services...
	poetry run python -c "import time; time.sleep(10)"
	$(BLANK)
	@echo [dev] Infrastructure ready:
	@echo       Qdrant dashboard : http://localhost:6333/dashboard
	@echo       RedisInsight     : http://localhost:8001
	$(BLANK)
	@echo [dev] Starting FastAPI with hot-reload...
	@echo       App    : http://127.0.0.1:8080
	@echo       Swagger: http://127.0.0.1:8080/docs
	$(BLANK)
	poetry run python src/app/main.py

# ── QA — fully containerised ──────────────────────────────────────────────────
qa:
	-podman machine start
	@echo [qa] Building and starting all QA containers...
	$(COMPOSE) --profile qa up --build -d
	@echo [qa] Waiting 15s for services...
	poetry run python -c "import time; time.sleep(15)"
	$(BLANK)
	@echo [qa] All services running:
	@echo      App     : http://localhost:8080
	@echo      Swagger : http://localhost:8080/docs
	@echo      Qdrant  : http://localhost:6333/dashboard
	@echo      Redis   : http://localhost:8001
	$(BLANK)
	@echo      Tail logs: make logs-qa

# ── PROD — fully containerised ────────────────────────────────────────────────
prod:
	-podman machine start
	@echo [prod] Building and starting production containers...
	$(COMPOSE) --profile prod up --build -d
	@echo [prod] Waiting 15s for services...
	poetry run python -c "import time; time.sleep(15)"
	$(BLANK)
	@echo [prod] Production running at http://localhost:8080
	@echo        Swagger UI is DISABLED in production.
	@echo        Tail logs: make logs-prod

# ── Stop ──────────────────────────────────────────────────────────────────────
stop-dev:
	@echo [stop] Stopping dev containers...
	$(COMPOSE) --profile dev down
	@echo [stop] Done. Data volumes are preserved.

stop-qa:
	@echo [stop] Stopping QA containers...
	$(COMPOSE) --profile qa down
	@echo [stop] Done. Data volumes are preserved.

stop-prod:
	@echo [stop] Stopping prod containers...
	$(COMPOSE) --profile prod down
	@echo [stop] Done. Data volumes are preserved.

# ── Ingest ────────────────────────────────────────────────────────────────────
ingest:
	@echo [ingest] Loading documents into Qdrant...
	poetry run python -m src.app.rag.ingestion.ingest

ingest-dry:
	@echo [ingest] Dry run - validating documents only...
	poetry run python -m src.app.rag.ingestion.ingest --dry-run

# ── Logs ──────────────────────────────────────────────────────────────────────
logs-qa:
	$(COMPOSE) --profile qa logs -f

logs-prod:
	$(COMPOSE) --profile prod logs -f

# ── Test ──────────────────────────────────────────────────────────────────────
test:
	@echo [test] Running tests...
	poetry run pytest tests/ -v

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	@echo [clean] Removing containers (volumes preserved)...
	$(COMPOSE) --profile dev --profile qa --profile prod down
	@echo [clean] Done.