from fastapi import APIRouter, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app import settings
from app.chatbot import generate_chat_response


# changed by akilu - protected chatbot API route
router = APIRouter(prefix="/chat", tags=["chat"])
bearer_scheme = HTTPBearer()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    answer: str
    model: str


@router.post("/message", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    _credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
):
    try:
        answer = generate_chat_response(payload.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc

    return ChatResponse(answer=answer, model=settings.llm_model)
