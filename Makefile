PYTHON ?= python
# Akilu changed this because Make targets should use native Podman commands through one launcher.
PODMAN_STACK = sh scripts/podman-stack.sh

.PHONY: help setup infra dev stack stop logs setup-collection ingest ingest-dry test

.DEFAULT_GOAL := help

help:
	@echo Insurance RAG Chatbot
	@echo
	@echo make setup             Install Python development dependencies
	@echo make infra             Start Qdrant, Redis, and Ollama
	@echo make dev               Start infrastructure and local API
	@echo make stack             Build and start the complete Podman stack
	@echo make stop              Stop the Podman stack
	@echo make setup-collection  Create the Qdrant collection
	@echo make ingest            Ingest policy documents
	@echo make ingest-dry        Validate policy documents without writing
	@echo make test              Run complete local chatbot tests

setup:
	$(PYTHON) -m pip install -e ".[dev]"

infra:
	$(PODMAN_STACK) infra

dev: infra
	$(PYTHON) -m uvicorn app.main:app --app-dir src --host 127.0.0.1 --port 8080 --reload

stack:
	$(PODMAN_STACK) up

stop:
	$(PODMAN_STACK) down

logs:
	$(PODMAN_STACK) logs

setup-collection:
	$(PYTHON) src/app/rag/setup.py

ingest:
	$(PYTHON) scripts/ingest.py

ingest-dry:
	$(PYTHON) scripts/ingest.py --dry-run

test:
	$(PYTHON) scripts/test_all.py
