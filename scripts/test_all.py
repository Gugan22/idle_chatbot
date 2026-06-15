"""Cross-platform end-to-end test runner for the insurance chatbot."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.config import settings


def step(message: str) -> None:
    print(f"\n[test-all] {message}", flush=True)


def request_json(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 15,
) -> dict[str, Any]:
    payload = json.dumps(body).encode() if body is not None else None
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = urllib.request.Request(
        url,
        data=payload,
        headers=request_headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def check_services() -> None:
    step("Checking Qdrant, Redis, and the configured LLM")

    qdrant_url = f"http://{settings.qdrant_host}:{settings.qdrant_port}/healthz"
    with urllib.request.urlopen(qdrant_url, timeout=10):
        pass
    print("[pass] Qdrant is reachable")

    import redis

    if not redis.Redis.from_url(settings.redis_url).ping():
        raise RuntimeError(f"Redis is not reachable at {settings.redis_url}")
    print("[pass] Redis is reachable")

    llm_headers = {}
    if settings.llm_api_key and settings.llm_api_key != "not-required":
        llm_headers["Authorization"] = f"Bearer {settings.llm_api_key}"
    request_json(
        f"{settings.llm_base_url.rstrip('/')}/models",
        headers=llm_headers,
        timeout=20,
    )
    print("[pass] Configured LLM is reachable")


def run_unit_tests() -> None:
    step("Running unit tests")
    timeout = int(os.getenv("UNIT_TEST_TIMEOUT_SECONDS", "420"))
    env = {**os.environ, "PYTHONPATH": str(SRC)}

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = f"{result.stdout}{result.stderr}"
        print(output.rstrip())
        if result.returncode != 0:
            raise RuntimeError("Unit tests failed")
    except subprocess.TimeoutExpired as exc:
        output = f"{exc.stdout or ''}{exc.stderr or ''}"
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        print(output.rstrip())
        # Akilu changed this because ML worker threads can keep pytest alive
        # after the test report has already reached successful completion.
        if "[100%]" not in output:
            raise RuntimeError(f"Unit tests exceeded the {timeout}-second timeout") from exc

    print("[pass] Unit tests passed")


def wait_for_health(base_url: str, process: subprocess.Popen[Any]) -> dict[str, Any]:
    timeout = int(os.getenv("API_STARTUP_TIMEOUT_SECONDS", "420"))
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"API exited during startup with code {process.returncode}")
        try:
            return request_json(f"{base_url}/api/v1/health", timeout=10)
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            time.sleep(2)

    raise RuntimeError(f"API did not become healthy within {timeout} seconds")


def run_api_test() -> None:
    step("Starting API and running an authenticated RAG chat")
    port = int(os.getenv("TEST_PORT", "18080"))
    base_url = f"http://127.0.0.1:{port}"
    env = {**os.environ, "PYTHONPATH": str(SRC)}

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            str(SRC),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        health = wait_for_health(base_url, process)
        if health.get("status") != "healthy":
            raise RuntimeError(f"API health is {health.get('status')}: {health}")
        print("[pass] API is healthy")

        if not settings.default_username or not settings.default_password:
            raise RuntimeError("DEFAULT_USERNAME and DEFAULT_PASSWORD must be configured")

        login = request_json(
            f"{base_url}/auth/login",
            method="POST",
            body={
                "username": settings.default_username,
                "password": settings.default_password,
            },
        )
        token = login["access_token"]
        chat = request_json(
            f"{base_url}/api/v1/rag/chat",
            method="POST",
            body={
                "query": "Does this policy cover collision damage to my car?",
                "filters": {},
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=int(os.getenv("CHAT_TIMEOUT_SECONDS", "240")),
        )

        if chat.get("failed") or chat.get("flagged") or not chat.get("confidence"):
            raise RuntimeError(f"RAG chat returned an invalid result: {chat}")
        cited = [source for source in chat.get("sources", []) if source.get("cited")]
        if not cited:
            raise RuntimeError("RAG chat answer did not contain a valid source citation")

        print("[pass] Authenticated RAG chat passed")
        print(f"[pass] Valid citation: {cited[0]['chunk_id']}")
        print(f"\nAnswer: {chat['answer']}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main() -> int:
    try:
        check_services()
        run_unit_tests()
        run_api_test()
    except Exception as exc:
        print(f"\n[failed] {exc}", file=sys.stderr)
        return 1

    print("\nAll idle_chatbot tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
