# JWT Authorization middleware and helper
import os
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import JSONResponse
import jwt

# env values
AUTH_SECRET = os.getenv("AUTH_SECRET")  # required for signing tokens
ALLOWED_PREFIXES = [
	"/auth",
	"/docs",
	"/openapi.json",
	"/docs/oauth2-redirect",
]


class JWTAuthMiddleware:
	"""ASGI middleware that validates Authorization: Bearer <token> JWTs.

	- Skips validation for paths starting with prefixes in ALLOWED_PREFIXES (e.g. /auth)
	- Decodes and verifies HS256-signed JWT using AUTH_SECRET
	- Verifies expiration (exp claim)
	- Attaches payload to scope['auth'] for downstream handlers
	"""

	def __init__(self, app: ASGIApp):
		self.app = app

	async def __call__(self, scope: Scope, receive: Receive, send: Send):
		# Only handle HTTP requests
		if scope["type"] != "http":
			await self.app(scope, receive, send)
			return

		path = scope.get("path", "")
		for p in ALLOWED_PREFIXES:
			if path.startswith(p):
				await self.app(scope, receive, send)
				return

		# Ensure secret is configured
		if not AUTH_SECRET:
			resp = JSONResponse({"detail": "Server auth secret not configured"}, status_code=500)
			await resp(scope, receive, send)
			return

		# Extract Authorization header
		headers = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
		auth = headers.get("authorization")
		if not auth or not auth.lower().startswith("bearer "):
			resp = JSONResponse({"detail": "Missing or invalid Authorization header"}, status_code=401)
			await resp(scope, receive, send)
			return

		token = auth.split(None, 1)[1].strip()
		try:
			payload = jwt.decode(token, AUTH_SECRET, algorithms=["HS256"])  # raises on invalid/expired
		except jwt.ExpiredSignatureError:
			resp = JSONResponse({"detail": "Token expired"}, status_code=401)
			await resp(scope, receive, send)
			return
		except Exception:
			resp = JSONResponse({"detail": "Invalid token"}, status_code=401)
			await resp(scope, receive, send)
			return

		# Attach auth payload to scope for downstream usage
		scope["auth"] = payload
		await self.app(scope, receive, send)


def require_permission(permission: str):
	"""Dependency factory for FastAPI endpoints. Usage:

	@router.get(..., dependencies=[Depends(require_permission('read:docs'))])

	It reads the token payload attached to request.scope['auth'] by the middleware and
	raises 403 if the permission is missing.
	"""

	from fastapi import Request, HTTPException, Depends

	async def _checker(request: Request):
		payload = request.scope.get("auth")
		if not payload:
			raise HTTPException(status_code=401, detail="Not authenticated")
		perms = payload.get("permissions", []) or []
		if permission not in perms:
			raise HTTPException(status_code=403, detail="Insufficient permissions")
		return payload

	return Depends(_checker)


