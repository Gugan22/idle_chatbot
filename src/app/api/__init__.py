from app.api.authApi import router as auth_router
# changed by akilu - export chat router for app startup
from app.api.chatApi import router as chat_router

__all__ = ["auth_router", "chat_router"]
