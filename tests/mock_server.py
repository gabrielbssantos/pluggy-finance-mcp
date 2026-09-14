"""Test-only subprocess entrypoint. Never packaged in the production container."""

import httpx
from conftest import FixtureAPI, settings

from pluggy_finance_mcp.client.http import PluggyClient
from pluggy_finance_mcp.server import build_server, configure_logging

if __name__ == "__main__":
    config = settings()
    server, _ = build_server(config, PluggyClient(config, httpx.MockTransport(FixtureAPI())))
    configure_logging()
    server.run(transport="stdio")
