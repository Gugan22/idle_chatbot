#!/usr/bin/env sh
# Akilu changed this because Linux and macOS should use the same native Podman-only workflow.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENV_FILE="$ROOT/.env"
NETWORK="idle-chatbot-net"
API_IMAGE="localhost/idle-chatbot-api:local"
ACTION="${1:-up}"

command -v podman >/dev/null 2>&1 || {
  echo "Podman is not installed or is not available on PATH." >&2
  exit 1
}

config_value() {
  name=$1
  default=$2
  eval "current=\${$name:-}"
  if [ -n "$current" ]; then printf '%s' "$current"; return; fi
  if [ -f "$ENV_FILE" ]; then
    value=$(sed -n "s/^${name}=//p" "$ENV_FILE" | tail -n 1)
    if [ -n "$value" ]; then printf '%s' "$value"; return; fi
  fi
  printf '%s' "$default"
}

container_exists() { podman container exists "$1" >/dev/null 2>&1; }
ensure_network() { podman network exists "$NETWORK" >/dev/null 2>&1 || podman network create "$NETWORK" >/dev/null; }
ensure_volume() { podman volume exists "$1" >/dev/null 2>&1 || podman volume create "$1" >/dev/null; }
start_existing() { container_exists "$1" && podman start "$1" >/dev/null; }

wait_for() {
  service=$1
  shift
  count=0
  until "$@" >/dev/null 2>&1; do
    count=$((count + 1))
    [ "$count" -lt 120 ] || { echo "$service did not become ready." >&2; exit 1; }
    sleep 2
  done
}

http_ready() {
  url=$1
  if command -v curl >/dev/null 2>&1; then
    curl -fsS "$url" >/dev/null
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O - "$url" >/dev/null
  elif command -v python3 >/dev/null 2>&1; then
    python3 - "$url" <<'PY'
import sys
import urllib.request

urllib.request.urlopen(sys.argv[1], timeout=3).read()
PY
  else
    echo "curl, wget, or python3 is required to check HTTP readiness." >&2
    return 1
  fi
}

start_infra() {
  ensure_network
  ensure_volume idle-chatbot-qdrant
  ensure_volume idle-chatbot-redis
  ensure_volume idle-chatbot-ollama

  if ! start_existing insurance-qdrant; then
    podman run -d --name insurance-qdrant --network "$NETWORK" \
      --label io.idle-chatbot.stack=true \
      -p "127.0.0.1:$(config_value QDRANT_PORT 6333):6333" \
      -p "127.0.0.1:$(config_value QDRANT_GRPC_PORT 6334):6334" \
      -v idle-chatbot-qdrant:/qdrant/storage:U \
      "$(config_value QDRANT_IMAGE docker.io/qdrant/qdrant:v1.12.5)"
  fi
  if ! start_existing insurance-redis; then
    podman run -d --name insurance-redis --network "$NETWORK" \
      --label io.idle-chatbot.stack=true \
      -p "127.0.0.1:$(config_value REDIS_PORT 6379):6379" \
      -v idle-chatbot-redis:/data:U \
      "$(config_value REDIS_IMAGE docker.io/library/redis:7.4-alpine)"
  fi
  if ! start_existing insurance-ollama; then
    podman run -d --name insurance-ollama --network "$NETWORK" \
      --label io.idle-chatbot.stack=true \
      -p "127.0.0.1:$(config_value OLLAMA_PORT 11434):11434" \
      -v idle-chatbot-ollama:/root/.ollama:U \
      "$(config_value OLLAMA_IMAGE docker.io/ollama/ollama:0.5.7)"
  fi

  wait_for Qdrant http_ready "http://127.0.0.1:$(config_value QDRANT_PORT 6333)/healthz"
  wait_for Redis podman exec insurance-redis redis-cli ping
  wait_for Ollama podman exec insurance-ollama ollama list
  podman exec insurance-ollama ollama pull "$(config_value LLM_MODEL phi3:latest)"
}

remove_stack() {
  for name in insurance-api insurance-ollama insurance-redis insurance-qdrant; do
    container_exists "$name" && podman rm -f "$name" >/dev/null
  done
}

start_stack() {
  start_infra
  ensure_volume idle-chatbot-model-cache
  cd "$ROOT"
  podman build -f Containerfile -t "$API_IMAGE" .

  podman run --rm --network "$NETWORK" \
    -e QDRANT_HOST=insurance-qdrant -e QDRANT_PORT=6333 \
    -e "COLLECTION_NAME=$(config_value COLLECTION_NAME insurance_policies)" \
    -e "EMBED_DIM=$(config_value EMBED_DIM 384)" \
    "$API_IMAGE" python src/app/rag/setup.py

  podman run --rm --network "$NETWORK" \
    -e QDRANT_HOST=insurance-qdrant -e QDRANT_PORT=6333 \
    -e "COLLECTION_NAME=$(config_value COLLECTION_NAME insurance_policies)" \
    -e "EMBED_MODEL=$(config_value EMBED_MODEL sentence-transformers/all-MiniLM-L6-v2)" \
    -e "EMBED_DIM=$(config_value EMBED_DIM 384)" -e EMBED_LOCAL_FILES_ONLY=false \
    -v idle-chatbot-model-cache:/home/appuser/.cache/huggingface:U \
    "$API_IMAGE" python scripts/ingest.py

  container_exists insurance-api && podman rm -f insurance-api >/dev/null
  if [ -f "$ENV_FILE" ]; then
    podman run -d --name insurance-api --network "$NETWORK" \
      --label io.idle-chatbot.stack=true \
      -p "$(config_value BIND_ADDRESS 127.0.0.1):$(config_value PORT 8080):8080" \
      --env-file "$ENV_FILE" \
      -e HOST=0.0.0.0 -e PORT=8080 \
      -e QDRANT_HOST=insurance-qdrant -e QDRANT_PORT=6333 \
      -e REDIS_URL=redis://insurance-redis:6379 \
      -e LLM_BASE_URL=http://insurance-ollama:11434/v1 \
      -e EMBED_LOCAL_FILES_ONLY=false \
      -v idle-chatbot-model-cache:/home/appuser/.cache/huggingface:U \
      "$API_IMAGE"
  else
    podman run -d --name insurance-api --network "$NETWORK" \
      --label io.idle-chatbot.stack=true \
      -p "$(config_value BIND_ADDRESS 127.0.0.1):$(config_value PORT 8080):8080" \
      -e HOST=0.0.0.0 -e PORT=8080 \
      -e QDRANT_HOST=insurance-qdrant -e QDRANT_PORT=6333 \
      -e REDIS_URL=redis://insurance-redis:6379 \
      -e LLM_BASE_URL=http://insurance-ollama:11434/v1 \
      -e EMBED_LOCAL_FILES_ONLY=false \
      -v idle-chatbot-model-cache:/home/appuser/.cache/huggingface:U \
      "$API_IMAGE"
  fi
}

case "$ACTION" in
  up) start_stack ;;
  infra) start_infra ;;
  down) remove_stack ;;
  restart) remove_stack; start_stack ;;
  logs) podman logs -f insurance-api ;;
  status) podman ps -a --filter label=io.idle-chatbot.stack=true ;;
  *) echo "Usage: $0 {up|infra|down|restart|logs|status}" >&2; exit 2 ;;
esac
