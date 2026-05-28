from __future__ import annotations

from functools import lru_cache

from app import settings


# changed by akilu - basic LangChain chatbot wrapper
SYSTEM_PROMPT = (
    "You are a helpful insurance chatbot. Answer clearly and concisely. "
    "If you do not know something, say so instead of guessing. "
    "The RAG engine is not connected yet, so do not claim to have searched policy documents."
)


@lru_cache(maxsize=1)
def _get_llm():
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError(
            "LangChain chat dependencies are not installed. "
            "Run: poetry install or pip install langchain-openai langchain-core"
        ) from exc

    return ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout_seconds,
    )


def generate_chat_response(message: str) -> str:
    if not message or not message.strip():
        raise ValueError("message cannot be empty")

    from langchain_core.messages import HumanMessage, SystemMessage

    llm = _get_llm()
    response = llm.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=message.strip()),
        ]
    )

    return str(response.content)
