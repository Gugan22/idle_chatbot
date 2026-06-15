"""OpenAI-compatible LLM client used by the RAG chat endpoint."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from openai import OpenAI

from app.config import settings


@lru_cache(maxsize=1)
def _get_client() -> OpenAI:
    return OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout_seconds,
    )


def generate(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate an answer using Ollama, NVIDIA NIM, or another compatible API."""
    try:
        response = _get_client().chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        answer = response.choices[0].message.content or ""
        return {"answer": answer.strip(), "failed": False}
    except Exception as exc:
        # Akilu changed this because an unavailable LLM should produce a stable
        # API response instead of crashing the complete RAG request.
        return {
            "answer": "The chatbot is temporarily unavailable. Please try again shortly.",
            "failed": True,
            "error": str(exc),
        }


def llm_health() -> dict[str, str]:
    """Return basic configuration health without generating billable output."""
    try:
        _get_client().models.list()
        return {"status": "ok", "model": settings.llm_model}
    except Exception as exc:
        return {"status": "error", "detail": str(exc), "model": settings.llm_model}
