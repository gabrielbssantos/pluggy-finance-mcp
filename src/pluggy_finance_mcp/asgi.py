from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.auth.provider import TokenVerifier
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp

from pluggy_finance_mcp.auth.mcp import AuthorizationHeaderGuardMiddleware, OidcJwtVerifier
from pluggy_finance_mcp.config import Settings
from pluggy_finance_mcp.server import Runtime, build_server, configure_logging


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def create_app(
    settings: Settings | None = None,
    server: FastMCP | None = None,
    token_verifier: TokenVerifier | None = None,
    runtime: Runtime | None = None,
) -> ASGIApp:
    settings = settings or Settings()
    if settings.mcp_transport != "streamable-http" or settings.mcp_auth_mode != "oauth":
        raise ValueError("HTTP requires OAuth configuration")
    if server is not None and token_verifier is None:
        raise ValueError("An injected server requires its OAuth token verifier")
    token_verifier = token_verifier or OidcJwtVerifier(settings)
    if server is None:
        server, runtime = build_server(settings, token_verifier=token_verifier)
    configure_logging()
    app = server.streamable_http_app()
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: Starlette) -> AsyncIterator[None]:
        try:
            async with original_lifespan(application):
                yield None
        finally:
            try:
                if runtime is not None:
                    await runtime.client.close()
            finally:
                close = getattr(token_verifier, "aclose", None)
                if close is not None:
                    result = close()
                    if hasattr(result, "__await__"):
                        await result

    app.router.lifespan_context = lifespan
    app.routes.extend([Route("/healthz", health), Route("/readyz", health)])
    app.user_middleware.insert(0, Middleware(AuthorizationHeaderGuardMiddleware))
    app.user_middleware.insert(0, Middleware(TrustedHostMiddleware, allowed_hosts=settings.hosts))
    return app
