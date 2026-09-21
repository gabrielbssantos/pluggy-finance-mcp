import asyncio
import json
import logging

import httpx
import pytest
from conftest import BANK, BILL, CARD, FOREIGN, INVESTMENT, ITEM, TRANSACTION, settings
from pydantic import ValidationError

from pluggy_finance_mcp.client.http import retry_delay
from pluggy_finance_mcp.client.pagination import pagination
from pluggy_finance_mcp.errors import FinanceError
from pluggy_finance_mcp.server import Runtime, build_server, configure_logging

CASES = [
    ("get_item", {}),
    ("get_sync_status", {}),
    ("get_connection_status", {}),
    ("list_accounts", {}),
    ("get_account", {"account_id": BANK}),
    ("get_account_balance", {"account_id": BANK}),
    ("list_account_statements", {"account_id": BANK}),
    ("list_transactions", {"account_id": BANK}),
    ("get_transaction", {"transaction_id": TRANSACTION}),
    ("list_credit_card_bills", {"account_id": CARD}),
    ("get_credit_card_bill", {"bill_id": BILL}),
    ("list_investments", {}),
    ("get_investment", {"investment_id": INVESTMENT}),
    ("list_investment_transactions", {"investment_id": INVESTMENT}),
    ("get_total_balance", {}),
    ("get_monthly_expenses", {"month": "2026-09"}),
    ("get_expenses_by_category", {"month": "2026-09"}),
    ("get_credit_card_summary", {}),
    ("get_investment_portfolio", {}),
    ("get_net_worth", {}),
]
CASES = [(name, {"item_id": ITEM, **args}) for name, args in CASES]


@pytest.mark.parametrize("tool,arguments", CASES)
async def test_all_tools_via_mcp(client_api, tool, arguments):
    client, api = client_api
    server, _ = build_server(client.settings, client)
    content, structured = await server.call_tool(tool, arguments)
    assert structured["ok"], structured
    assert structured["tool"] == tool
    assert content
    output = json.dumps(structured)
    for secret in [
        "PRIVATE_OWNER",
        "PRIVATE_CPF",
        "PRIVATE_API_KEY",
        "PRIVATE_PASSWORD",
        "PRIVATE_ACCOUNT_NUMBER",
    ]:
        assert secret not in output
    assert all(r.method == "GET" or r.url.path == "/auth" for r in api.requests)


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE", "PUT", "HEAD"])
async def test_no_write_before_network(client_api, method):
    client, api = client_api
    with pytest.raises(FinanceError, match="FORBIDDEN"):
        await client.get("account", BANK, method=method)
    assert not api.requests


@pytest.mark.parametrize(
    "operation,identifier,params",
    [
        ("https://evil.invalid", None, {}),
        ("/payments", None, {}),
        ("account", "../../auth", {}),
        ("account", BANK, {"url": "https://evil.invalid"}),
    ],
)
async def test_no_generic_executor(client_api, operation, identifier, params):
    client, api = client_api
    with pytest.raises(FinanceError):
        await client.get(operation, identifier, params)
    assert not api.requests


async def test_foreign_account_and_descendants(client_api):
    client, api = client_api
    runtime = Runtime(client.settings, client)
    for tool in [
        "get_account",
        "get_account_balance",
        "list_transactions",
        "list_account_statements",
    ]:
        result = await runtime.invoke(tool, item_id=ITEM, account_id=FOREIGN)
        assert result.error["code"] == "NOT_FOUND"
        assert result.data is None
    assert not any(
        r.url.path.endswith("/balance") or r.url.path == "/v2/transactions" for r in api.requests
    )


async def test_foreign_transaction_and_bill(client_api):
    client, api = client_api
    api.transactions[BANK][0]["accountId"] = FOREIGN
    runtime = Runtime(client.settings, client)
    result = await runtime.invoke("get_transaction", item_id=ITEM, transaction_id=TRANSACTION)
    assert result.error["code"] == "NOT_FOUND"
    result = await runtime.invoke("get_credit_card_bill", item_id=ITEM, bill_id=FOREIGN)
    assert result.error["code"] == "NOT_FOUND"
    assert not any(r.url.path == f"/bills/{FOREIGN}" for r in api.requests)


async def test_foreign_list_row_never_returned(client_api):
    client, api = client_api
    api.accounts[0]["itemId"] = FOREIGN
    result = await Runtime(client.settings, client).invoke("list_accounts", item_id=ITEM)
    assert result.error["code"] == "NOT_FOUND"
    assert result.data is None


async def test_key_lock_and_expiry(client_api):
    client, api = client_api
    await asyncio.gather(*(client.get("item", ITEM) for _ in range(10)))
    assert api.auth_calls == 1
    client.auth._expires = 0
    await client.get("item", ITEM)
    assert api.auth_calls == 2


async def test_401_renews_only_once(client_api):
    client, api = client_api

    async def reject(request):
        if request.method == "GET":
            return httpx.Response(401)

    api.override = reject
    result = await Runtime(client.settings, client).invoke("list_accounts", item_id=ITEM)
    assert result.error["code"] == "UNAUTHENTICATED"
    assert api.auth_calls == 2
    assert sum(r.method == "GET" for r in api.requests) == 2


@pytest.mark.parametrize(
    "status,expected",
    [
        (403, "FORBIDDEN"),
        (404, "NOT_FOUND"),
        (429, "RATE_LIMITED"),
        (502, "UPSTREAM_UNAVAILABLE"),
        (503, "UPSTREAM_UNAVAILABLE"),
        (504, "UPSTREAM_TIMEOUT"),
        (500, "UPSTREAM_ERROR"),
    ],
)
async def test_errors_retries(client_api, status, expected):
    client, api = client_api

    async def failure(request):
        if request.method == "GET":
            return httpx.Response(
                status, headers={"Retry-After": "0"}, json={"private": "PRIVATE_UPSTREAM_BODY"}
            )

    api.override = failure
    result = await Runtime(client.settings, client).invoke("list_accounts", item_id=ITEM)
    assert result.error["code"] == expected
    assert sum(r.method == "GET" for r in api.requests) == (
        3 if status in {429, 502, 503, 504} else 1
    )
    assert "PRIVATE" not in result.model_dump_json()


async def test_redirect_never_followed(client_api):
    client, api = client_api

    async def redirect(request):
        if request.method == "GET":
            return httpx.Response(302, headers={"location": "https://evil.invalid/steal"})

    api.override = redirect
    result = await Runtime(client.settings, client).invoke("list_accounts", item_id=ITEM)
    assert not result.ok
    assert all(r.url.host == "api.pluggy.ai" for r in api.requests)


async def test_raw_timeout(client_api):
    client, api = client_api
    client.settings.pluggy_http_timeout_seconds = 0.02

    async def slow(request):
        if request.method == "GET":
            await asyncio.sleep(0.1)

    api.override = slow
    result = await Runtime(client.settings, client).invoke("list_accounts", item_id=ITEM)
    assert result.error["code"] == "UPSTREAM_TIMEOUT"


async def test_response_size_limit(client_api):
    client, api = client_api
    client.settings.max_response_bytes = 1024
    api.accounts[0]["name"] = "x" * 3000
    result = await Runtime(client.settings, client).invoke("list_accounts", item_id=ITEM)
    assert result.error["code"] == "UPSTREAM_ERROR"


@pytest.mark.parametrize(
    "next_value",
    [
        "https://evil.invalid/?after=x",
        "?after=x&accountId=foreign",
        "?after=x&after=y",
        "?after=x&url=evil",
        "?after=",
        "/v2/transactions?after=x",
    ],
)
def test_untrusted_next(next_value):
    with pytest.raises(FinanceError):
        pagination({"next": next_value}, BANK)


def test_cursor_is_opaque():
    assert pagination({"next": f"?accountId={BANK}&after=a%2Bb%3D"}, BANK)["next_cursor"] == "a+b="
    assert retry_delay("0", 1) == 0
    assert retry_delay("Thu, 01 Jan 1970 00:00:00 GMT", 1) == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mcp_transport": "streamable-http"},
        {"mcp_auth_mode": "none"},
        {"mcp_auth_mode": "bearer"},
        {"pluggy_base_url": "https://evil.invalid"},
        {"enable_identity_tool": True},
        {"log_pii": True},
        {"mcp_allowed_hosts": "*"},
        {"k_service": "cloud-service"},
    ],
)
def test_configuration_fail_closed(kwargs):
    with pytest.raises(ValidationError):
        settings(**kwargs)


@pytest.mark.parametrize(
    "overrides",
    [
        {"mcp_public_url": None},
        {"mcp_oauth_issuer_url": None},
        {"mcp_public_url": "http://mcp.example.test/mcp"},
        {"mcp_public_url": "https://user:password@mcp.example.test/mcp"},
        {"mcp_public_url": "https://mcp.example.test/wrong"},
        {"mcp_public_url": "https://other.example.test/mcp"},
        {"mcp_oauth_issuer_url": "http://identity.example.test"},
        {"mcp_oauth_allowed_subject": ""},
        {"mcp_oauth_allowed_client_ids": ""},
        {"mcp_oauth_allowed_client_ids": "client,*"},
        {"mcp_oauth_scope": "two scopes"},
        {"mcp_oauth_scope": 'invalid"scope'},
    ],
)
def test_remote_oauth_configuration_fail_closed(overrides):
    from conftest import remote_settings

    with pytest.raises(ValidationError):
        remote_settings(**overrides)


async def test_log_privacy(client_api, capsys):
    client, api = client_api
    configure_logging()
    logging.getLogger("httpx").error("PRIVATE_API_KEY PRIVATE_URL")
    await Runtime(client.settings, client).invoke("list_accounts", item_id=ITEM)
    captured = capsys.readouterr()
    assert not captured.out
    assert "list_accounts" in captured.err
    assert "PRIVATE" not in captured.err
    assert BANK not in captured.err
    # pytest owns stream handlers outside this focused test.
    logging.getLogger().handlers.clear()


async def test_tools_schema_and_annotations(client_api):
    client, _ = client_api
    server, _ = build_server(client.settings, client)
    tools = await server.list_tools()
    assert {t.name for t in tools} == {name for name, _ in CASES} | {"sync_item"}
    for tool in tools:
        assert tool.annotations.readOnlyHint == (tool.name != "sync_item")
        assert not tool.annotations.destructiveHint
        assert "item_id" in tool.inputSchema["required"]
        assert tool.outputSchema
    tx = next(t for t in tools if t.name == "list_transactions")
    assert "page_size" not in tx.inputSchema["properties"]


async def test_auth_failure_is_not_retried(client_api):
    client, api = client_api

    async def broken_auth(request):
        if request.url.path == "/auth":
            raise httpx.ConnectError("PRIVATE_NETWORK_DETAILS")

    api.override = broken_auth
    result = await Runtime(client.settings, client).invoke("list_accounts", item_id=ITEM)
    assert result.error["code"] == "UPSTREAM_UNAVAILABLE"
    assert len(api.requests) == 1


async def test_network_get_retries(client_api, monkeypatch):
    client, api = client_api
    from pluggy_finance_mcp.client import http

    monkeypatch.setattr(http, "retry_delay", lambda *args: 0)

    async def broken_get(request):
        if request.method == "GET":
            raise httpx.ReadTimeout("PRIVATE_NETWORK_DETAILS")

    api.override = broken_get
    result = await Runtime(client.settings, client).invoke("list_accounts", item_id=ITEM)
    assert result.error["code"] == "UPSTREAM_TIMEOUT"
    assert sum(r.method == "GET" for r in api.requests) == 3
    assert api.auth_calls == 1


async def test_parallel_401_only_one_replacement_key(client_api):
    client, api = client_api
    auth_calls = 0

    async def rotating(request):
        nonlocal auth_calls
        if request.url.path == "/auth":
            auth_calls += 1
            return httpx.Response(200, json={"apiKey": "key-" + str(auth_calls)})
        if request.headers["X-API-KEY"] == "key-1":
            await asyncio.sleep(0.01)
            return httpx.Response(401)
        return httpx.Response(200, json={"id": ITEM})

    api.override = rotating
    await asyncio.gather(*(client.get("item", ITEM) for _ in range(12)))
    assert auth_calls == 2
