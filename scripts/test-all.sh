#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON="$ROOT/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  PYTHON="${PYTHON:-python3}"
fi

cd "$ROOT"
exec "$PYTHON" scripts/test_all.py
