from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app import settings
import time
import jwt

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
	username: str
	password: str


class TokenResponse(BaseModel):
	access_token: str
	token_type: str = "bearer"


DEFAULT_USERNAME = settings.default_username
DEFAULT_PASSWORD = settings.default_password
AUTH_SECRET = settings.auth_secret
DEFAULT_TTL_SECONDS = settings.token_ttl_seconds


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest):
	if payload.username != DEFAULT_USERNAME or payload.password != DEFAULT_PASSWORD:
		raise HTTPException(status_code=401, detail="Invalid credentials")
	if not AUTH_SECRET:
		raise HTTPException(status_code=500, detail="Server auth secret not configured")

	now = int(time.time())
	exp = now + DEFAULT_TTL_SECONDS
	# Default permissions for this simple login — in real apps you'd look up per-user permissions
	permissions = ["rag:query", "chat:message"]
	payload_jwt = {"sub": payload.username, "iat": now, "exp": exp, "permissions": permissions}
	token = jwt.encode(payload_jwt, AUTH_SECRET, algorithm="HS256")
	return {"access_token": token, "token_type": "bearer"}


