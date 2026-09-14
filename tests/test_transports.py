import asyncio
import os
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from conftest import ITEM, TOKEN, settings
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from test_raw_security import CASES

from pluggy_finance_mcp.asgi import create_app
from pluggy_finance_mcp.server import build_server

ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def serving(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, timeout=5)
        sock.close()


async def test_stdio_and_http_same_schemas_and_execution(client_api, tmp_path):
    client, api = client_api
    config = settings(
        mcp_transport="streamable-http", mcp_auth_mode="bearer", mcp_bearer_token=TOKEN
    )
    server, runtime = build_server(config, client)
    app = create_app(config, server, runtime=runtime)
    async with serving(app) as url:
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {TOKEN}"}) as http:
            async with streamable_http_client(url + "/mcp", http_client=http) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    http_tools = (await session.list_tools()).tools
                    for tool, arguments in CASES:
                        result = await session.call_tool(tool, arguments)
                        assert not result.isError, result
                        assert result.structuredContent["ok"], result
                    # Repeated independent requests must not close the shared upstream client.
                    assert not client.http.is_closed
        async with httpx.AsyncClient() as health_client:
            assert (await health_client.get(url + "/healthz")).status_code == 200
    assert client.http.is_closed
    with (tmp_path / "stderr.txt").open("w+") as errlog:
        parameters = StdioServerParameters(
            command=sys.executable, args=[str(ROOT / "tests/mock_server.py")]
        )
        async with stdio_client(parameters, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                stdio_tools = (await session.list_tools()).tools
                for tool, arguments in CASES:
                    result = await session.call_tool(tool, arguments)
                    assert not result.isError and result.structuredContent["ok"]
        errlog.seek(0)
        stderr = errlog.read()
        assert "PRIVATE" not in stderr
        assert "pluggy_finance_mcp" not in stderr  # no traceback
    assert [t.model_dump() for t in stdio_tools] == [t.model_dump() for t in http_tools]
    assert all(r.method == "GET" or r.url.path == "/auth" for r in api.requests)


async def test_auth_hosts_origins_health():
    config = settings(
        mcp_transport="streamable-http", mcp_auth_mode="bearer", mcp_bearer_token=TOKEN
    )
    server, runtime = build_server(config)
    app = create_app(config, server, runtime=runtime)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://localhost"
        ) as http:
            assert (await http.get("/healthz")).json() == {"status": "ok"}
            assert (await http.get("/readyz")).status_code == 200
            for headers in [
                {},
                {"Authorization": "Bearer invalid"},
                {"Authorization": "Basic " + TOKEN},
            ]:
                assert (await http.post("/mcp", json={}, headers=headers)).status_code == 401
            response = await http.get("/healthz", headers={"Host": "evil.invalid"})
            assert response.status_code == 400
            response = await http.post(
                "/mcp",
                json={},
                headers={
                    "Authorization": "Bearer " + TOKEN,
                    "Origin": "https://evil.invalid",
                    "Accept": "application/json, text/event-stream",
                },
            )
            assert response.status_code == 403


async def test_real_entrypoint_discovery_and_eof(tmp_path):
    env = {
        "PLUGGY_CLIENT_ID": "synthetic",
        "PLUGGY_CLIENT_SECRET": "synthetic",
        "PLUGGY_ITEM_ID": ITEM,
        "MCP_TRANSPORT": "stdio",
    }
    with (tmp_path / "stderr").open("w+") as errlog:
        async with stdio_client(
            StdioServerParameters(
                command=sys.executable, args=["-m", "pluggy_finance_mcp"], env=env
            ),
            errlog=errlog,
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                assert len((await session.list_tools()).tools) == 18
    # Closing stdin must terminate a local server without a listener or external requests.
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "pluggy_finance_mcp",
        env={**os.environ, **env},
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(b""), timeout=5)
    assert proc.returncode == 0 and stdout == b""
    assert b"Traceback" not in stderr


async def test_configuration_error_never_prints_inputs():
    env = {
        k: v for k, v in os.environ.items() if not k.startswith(("PLUGGY_", "MCP_", "K_SERVICE"))
    }
    env["PLUGGY_CLIENT_SECRET"] = "PRIVATE_CONFIGURATION_SECRET"
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "pluggy_finance_mcp",
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    assert proc.returncode == 2
    assert stdout == b""
    assert b"PRIVATE" not in stderr
    assert b"CONFIGURATION_ERROR" in stderr
