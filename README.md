# Insurance RAG Chatbot

A FastAPI chatbot that answers auto and homeowners insurance questions using
policy documents stored in Qdrant. It uses Redis for semantic caching and any
OpenAI-compatible LLM endpoint, including Ollama, NVIDIA NIM, and OpenAI.

## Components

- FastAPI API and browser chatbot at `/chat`
- Qdrant vector database
- Redis semantic response cache
- Sentence Transformers embedding and reranking models
- OpenAI-compatible LLM client
- Markdown policy ingestion with source citations

## Requirements

Choose one setup:

1. **Podman setup:** Podman only; no Compose provider is required
2. **Local setup:** Python 3.10-3.14, Qdrant, Redis, and an OpenAI-compatible LLM

The first startup downloads embedding, reranking, and LLM models. It can take
several minutes and requires internet access.

## Configuration

Create a local configuration before starting:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Change these values in `.env`:

```dotenv
AUTH_SECRET=use-a-random-secret-with-at-least-32-characters
DEFAULT_USERNAME=your-username
DEFAULT_PASSWORD=use-a-strong-password
INGEST_API_KEY=use-a-random-key-with-at-least-32-characters
```

Never commit `.env`. Production startup rejects known defaults and weak
credentials.

An installed package looks for `.env` in its launch directory. Set `ENV_FILE`
to an absolute file path when configuration lives elsewhere.

## Complete Podman Setup

The native Podman script starts Qdrant, Redis, Ollama, downloads the configured LLM,
creates the Qdrant collection, ingests documents, and starts the API.

Windows one-command startup:

```powershell
.\podman-idle-chatbot.cmd
```

Linux or macOS one-command startup:

```bash
sh scripts/podman-stack.sh up
```

Open:

- Chatbot: `http://127.0.0.1:8080/chat`
- API docs in development: `http://127.0.0.1:8080/docs`

Useful launcher actions:

```powershell
.\podman-idle-chatbot.cmd status
.\podman-idle-chatbot.cmd logs
.\podman-idle-chatbot.cmd restart
.\podman-idle-chatbot.cmd down
```

## Local Python Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
```

Windows:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Linux or macOS:

```bash
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Start infrastructure and prepare data:

```bash
sh scripts/podman-stack.sh infra
python src/app/rag/setup.py
python scripts/ingest.py
```

Start the API:

```bash
python -m uvicorn app.main:app --app-dir src --host 127.0.0.1 --port 8080
```

For access from other machines, use `--host 0.0.0.0` and place the API behind
an HTTPS reverse proxy and firewall.

For Podman container access from other machines, set `BIND_ADDRESS=0.0.0.0`. The
default binds published ports to loopback so infrastructure is not accidentally
exposed to a network.

## Using Another LLM

Set these variables in `.env`:

```dotenv
LLM_MODEL=your-model
LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
LLM_API_KEY=your-api-key
```

For the Podman API container, also set:

```dotenv
CONTAINER_LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
```

## Policy Documents

Place Markdown policy documents in:

```text
src/app/rag/docs/
```

Validate documents:

```bash
python scripts/ingest.py --dry-run
```

Ingest documents:

```bash
python scripts/ingest.py
```

## Testing

Cross-platform complete test:

```bash
python scripts/test_all.py
```

Convenience launchers:

```powershell
.\test-idle-chatbot.cmd
```

```bash
sh scripts/test-all.sh
```

The test runner reads hosts, credentials, ports, and model settings from the
configuration instead of using machine-specific values.

## Production Checklist

- Set `ENV=production`
- Generate unique authentication and ingestion secrets
- Use HTTPS through a reverse proxy
- Do not expose Qdrant, Redis, or Ollama ports publicly
- Restrict access with a firewall
- Back up Qdrant and Redis volumes
- Pin and review dependency/container updates
- Monitor API and model resource usage
