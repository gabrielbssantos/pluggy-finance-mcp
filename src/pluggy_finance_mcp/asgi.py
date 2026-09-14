from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp

from pluggy_finance_mcp.auth.mcp import AuthenticationMiddleware, BearerValidator, TokenValidator
from pluggy_finance_mcp.config import Settings
from pluggy_finance_mcp.server import Runtime, build_server, configure_logging


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def create_app(
    settings: Settings | None = None,
    server: FastMCP | None = None,
    validator: TokenValidator | None = None,
    runtime: Runtime | None = None,
) -> ASGIApp:
    settings = settings or Settings()
    if settings.mcp_transport != "streamable-http" or not settings.mcp_bearer_token:
        raise ValueError("HTTP requires authenticated HTTP configuration")
    if server is None:
        server, runtime = build_server(settings)
    configure_logging()
    app = server.streamable_http_app()
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: Starlette) -> AsyncIterator[None]:
        try:
            async with original_lifespan(application):
                yield None
        finally:
            if runtime is not None:
                await runtime.client.close()

    app.router.lifespan_context = lifespan
    app.routes.extend([Route("/healthz", health), Route("/readyz", health)])
    app.user_middleware.insert(
        0,
        Middleware(
            AuthenticationMiddleware,
            validator=validator or BearerValidator(settings.mcp_bearer_token.get_secret_value()),
        ),
    )
    app.user_middleware.insert(0, Middleware(TrustedHostMiddleware, allowed_hosts=settings.hosts))
    return app
