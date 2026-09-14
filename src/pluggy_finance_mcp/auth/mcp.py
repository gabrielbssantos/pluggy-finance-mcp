import secrets
from typing import Protocol

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class TokenValidator(Protocol):
    """Replace with issuer/audience/scope-aware OAuth verification for a future release."""

    async def valid(self, token: str) -> bool: ...


class BearerValidator:
    def __init__(self, token: str) -> None:
        self._token = token.encode()

    async def valid(self, token: str) -> bool:
        return secrets.compare_digest(token.encode(), self._token)


class AuthenticationMiddleware:
    def __init__(self, app: ASGIApp, validator: TokenValidator) -> None:
        self.app = app
        self.validator = validator

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] not in {"/healthz", "/readyz"}:
            values = [v for k, v in scope["headers"] if k.lower() == b"authorization"]
            accepted = False
            if len(values) == 1:
                value = values[0].decode("latin-1")
                scheme, _, token = value.partition(" ")
                if scheme.lower() == "bearer" and token:
                    accepted = await self.validator.valid(token)
            if not accepted:
                response = JSONResponse(
                    {"error": "UNAUTHENTICATED"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
