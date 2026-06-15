"""
src/app/rag/retrieval/prompt_builder.py
─────────────────────────────────────────────────────────────────────────────
Assembles the final prompt sent to the LLM.

Structure:
  [SYSTEM]
  You are a personal insurance assistant...
  Instructions on citing sources, staying on topic, not guessing...

  [CONTEXT BLOCK 1]
  Source: HOME-FIRE-TN-2024 | Section: What is covered | chunk_id: fire_tn_coverage_001
  The policy covers direct physical loss...

  [CONTEXT BLOCK 2]
  ...

  [USER]
  Does my policy cover damage to the attached garage?

Key design decisions:
  - Each chunk is labelled with policy_id, section_title, and chunk_id.
    This lets the LLM cite the exact clause it used in its answer, and
    lets the logging system trace which chunks contributed to each response.

  - Token budget is enforced. Nemotron 3 Super supports 262K tokens but
    we cap context at CONTEXT_MAX_TOKENS (default 8000) to keep responses
    fast and prevent runaway prompt assembly.

  - The system prompt explicitly instructs the LLM to:
    a) Only answer from the provided context
    b) Cite the chunk_id of any clause it references
    c) Say "I don't have that information" rather than guessing
    d) Never provide definitive legal or financial advice
    e) Stay strictly within auto and homeowners insurance topics
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[4]
SRC  = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.config import settings

# ── System prompt ─────────────────────────────────────────────────────────────
# Defines the LLM's role, constraints, and citation format.
# Keep this focused — long system prompts dilute instruction following.

# Akilu changed this because the knowledge base now contains both auto and
# homeowners coverage, so the assistant must support both product types.
SYSTEM_PROMPT = """You are a knowledgeable and professional personal insurance assistant \
for an insurance company.

Your role is to help policyholders understand their auto and homeowners insurance coverage, \
exclusions, claims process, and policy terms.

STRICT RULES — follow these exactly:
1. Answer ONLY from the policy context provided below. Do not use external knowledge.
2. If the context does not contain enough information to answer, say exactly:
   "I don't have specific information about that in our policy documents. \
Please contact our support team for assistance."
3. When you use information from a specific clause, cite it like this:
   [Source: {chunk_id}]
   Copy the provided chunk_id exactly. Never alter, abbreviate, or invent it.
4. Never provide definitive legal or financial advice. Use phrases like
   "according to your policy" or "based on the policy documents".
5. Stay strictly on the topic of auto and homeowners insurance. Politely decline any
   off-topic questions.
6. Do not fabricate policy numbers, coverage amounts, or claim timelines
   that are not explicitly stated in the context.
7. Be concise and clear. Policyholders may be stressed — avoid jargon.

The context below contains relevant sections from the policyholder's documents."""


def _estimate_tokens(text: str) -> int:
    """
    Rough token estimate: ~4 characters per token for English text.
    Used to enforce the context budget cap without a full tokeniser.
    Good enough for our purposes — we're not billing by the token here.
    """
    return len(text) // 4


def _format_chunk(chunk: dict[str, Any], index: int) -> str:
    """
    Format a single chunk as a labelled context block.

    Format:
        [Context 1]
        Source: HOME-FIRE-TN-2024 | Section: What is covered | ID: fire_tn_coverage_001
        The policy covers direct physical loss...
    """
    policy_id     = chunk.get("policy_id", "unknown")
    section_title = chunk.get("section_title", "")
    chunk_id      = chunk.get("chunk_id", "")
    text          = chunk.get("text", "").strip()
    rerank_score  = chunk.get("rerank_score", "")

    header_parts = [f"Source: {policy_id}"]
    if section_title:
        header_parts.append(f"Section: {section_title}")
    if chunk_id:
        header_parts.append(f"ID: {chunk_id}")

    header = " | ".join(header_parts)

    return f"[Context {index}]\n{header}\n{text}"


def build_prompt(
    query: str,
    chunks: list[dict[str, Any]],
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """
    Assemble the full prompt for the LLM.

    Args:
        query:         the user's original question
        chunks:        reranked chunks from reranker.rerank()
        system_prompt: override the default system prompt (optional)

    Returns:
        dict with:
          - messages        : list of {"role": ..., "content": ...} for the LLM API
          - context_chunks  : the chunks actually included (may be fewer than input
                              if token budget was hit)
          - estimated_tokens: rough token count of the full prompt
          - truncated       : True if some chunks were dropped due to token budget

    The messages format is OpenAI-compatible — works with Ollama, NVIDIA NIM,
    and the openai Python client without any changes.
    """
    sys_prompt = system_prompt or SYSTEM_PROMPT
    max_context_tokens = settings.context_max_tokens

    # ── Build context blocks respecting token budget ───────────────────────────
    context_blocks: list[str] = []
    included_chunks: list[dict[str, Any]] = []
    total_context_tokens = 0
    truncated = False

    for i, chunk in enumerate(chunks, start=1):
        block = _format_chunk(chunk, i)
        block_tokens = _estimate_tokens(block)

        if total_context_tokens + block_tokens > max_context_tokens:
            truncated = True
            print(
                f"[prompt_builder] Token budget hit at chunk {i}. "
                f"Dropping remaining {len(chunks) - i + 1} chunk(s)."
            )
            break

        context_blocks.append(block)
        included_chunks.append(chunk)
        total_context_tokens += block_tokens

    # ── Assemble the full context section ─────────────────────────────────────
    if context_blocks:
        context_section = (
            "--- POLICY CONTEXT ---\n\n"
            + "\n\n".join(context_blocks)
            + "\n\n--- END OF CONTEXT ---"
        )
    else:
        # No chunks passed — this shouldn't happen if is_confident() was checked,
        # but handle it gracefully just in case.
        context_section = (
            "--- POLICY CONTEXT ---\n"
            "No relevant policy information found for this query.\n"
            "--- END OF CONTEXT ---"
        )

    # ── Build messages in OpenAI chat format ──────────────────────────────────
    messages = [
        {
            "role":    "system",
            "content": f"{sys_prompt}\n\n{context_section}",
        },
        {
            "role":    "user",
            "content": query.strip(),
        },
    ]

    # ── Estimate total tokens ──────────────────────────────────────────────────
    total_tokens = (
        _estimate_tokens(sys_prompt)
        + total_context_tokens
        + _estimate_tokens(query)
    )

    return {
        "messages":         messages,
        "context_chunks":   included_chunks,
        "estimated_tokens": total_tokens,
        "truncated":        truncated,
    }


def build_no_context_response() -> str:
    """
    Standard fallback message when retrieval confidence is too low.
    Returned directly to the user — LLM is not called.
    """
    return (
        "I don't have specific information about that in our policy documents. "
        "Please contact our support team or your insurance advisor for assistance."
    )


def extract_cited_chunks(answer: str, chunks: list[dict[str, Any]]) -> list[str]:
    """
    Parse the LLM's answer to find which chunk_ids were actually cited.
    Used by the logging system and the /chat response schema.

    The LLM is instructed to cite like: [Source: chunk_id_here]
    This function extracts those IDs from the answer text.

    Returns:
        List of chunk_ids that appear in the answer.
    """
    import re
    cited_ids: list[str] = []
    chunk_id_set = {c.get("chunk_id", "") for c in chunks}

    # Match [Source: some_chunk_id]
    pattern = re.compile(r"\[Source:\s*([^\]]+)\]")
    for match in pattern.finditer(answer):
        cited_id = match.group(1).strip()
        if cited_id in chunk_id_set:
            cited_ids.append(cited_id)

    return list(dict.fromkeys(cited_ids))  # deduplicate preserving order
