"""Read-only MCP discovery; optionally call synthetic tools in a test-only subprocess."""

import argparse
import asyncio
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def run(python: str, mock: bool) -> None:
    root = ROOT
    args = [str(root / "tests/mock_server.py")] if mock else ["-m", "pluggy_finance_mcp"]
    env = {
        "PLUGGY_CLIENT_ID": "synthetic-client",
        "PLUGGY_CLIENT_SECRET": "synthetic-secret",
        "MCP_TRANSPORT": "stdio",
    }
    async with stdio_client(StdioServerParameters(command=python, args=args, env=env)) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            assert len(tools) == 21
            if mock:
                # The calling interpreter (e.g. Hermes) does not need project's test dependencies.
                cases = [
                    ("list_accounts", {}),
                    ("get_monthly_expenses", {"month": "2026-09"}),
                    ("get_net_worth", {}),
                ]
                for name, arguments in cases:
                    result = await session.call_tool(
                        name, {"item_id": "00000000-0000-0000-0000-000000000001", **arguments}
                    )
                    payload = result.model_dump(by_alias=True)
                    assert not payload.get("isError", False)
                    assert payload["structuredContent"]["ok"]
    print("MCP stdio: 21 tools discovered" + ("; synthetic calls passed" if mock else ""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--python", default=str(Path(__file__).resolve().parents[1] / ".venv/bin/python")
    )
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.python, args.mock))
