"""Lightweight input and output checks for the insurance chatbot."""

from __future__ import annotations

from typing import Any


INSURANCE_TERMS = {
    "insurance", "policy", "coverage", "cover", "claim", "deductible",
    "premium", "liability", "collision", "comprehensive", "home", "house",
    "auto", "car", "vehicle", "fire", "flood", "theft", "damage",
}


def run_input_guard(query: str) -> dict[str, Any]:
    """Reject empty and clearly off-topic requests before retrieval."""
    cleaned = query.strip()
    if not cleaned:
        return {
            "blocked": True,
            "reason": "empty_query",
            "message": "Please enter an insurance-related question.",
        }

    # Akilu changed this because unrelated prompts should not consume embedding,
    # retrieval, reranking, and LLM resources.
    lowered = cleaned.lower()
    if not any(term in lowered for term in INSURANCE_TERMS):
        return {
            "blocked": True,
            "reason": "off_topic",
            "message": "I can only help with auto and homeowners insurance questions.",
        }

    return {"blocked": False, "reason": None, "message": ""}


def check_output(answer: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Flag empty answers or unsupported answers that cite no retrieved source."""
    cleaned = answer.strip()
    if not cleaned:
        return {
            "answer": "The chatbot could not generate an answer. Please try again.",
            "flagged": True,
        }

    known_ids = {str(chunk.get("chunk_id", "")) for chunk in chunks}
    cited = any(f"[Source: {chunk_id}]" in cleaned for chunk_id in known_ids if chunk_id)
    no_context_answer = "I don't have specific information about that" in cleaned

    # Akilu changed this because factual insurance answers should identify the
    # retrieved policy chunk supporting them.
    return {"answer": cleaned, "flagged": not cited and not no_context_answer}
