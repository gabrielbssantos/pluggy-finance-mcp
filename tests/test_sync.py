import asyncio
import json

import httpx
import pytest
from conftest import FOREIGN, ITEM, settings

from pluggy_finance_mcp.client.http import PluggyClient
from pluggy_finance_mcp.server import Runtime, build_server


def item(status="UPDATED", execution="SUCCESS", identifier=ITEM):
    return {
        "id": identifier,
        "status": status,
        "executionStatus": execution,
        "lastUpdatedAt": "2026-09-15T12:00:00Z",
        "connector": {"id": 1, "name": "Synthetic", "credentials": "PRIVATE"},
        "parameters": {"password": "PRIVATE"},
    }


@pytest.fixture
def setup(client_api):
    client, api = client_api
    client.settings.pluggy_sync_poll_interval_seconds = 0.001
    return client, api, Runtime(client.settings, client)


def install(api, states, patch=None):
    states = iter(states)
    latest = None

    async def handler(request):
        nonlocal latest
        if request.url.path.startswith("/items/"):
            if request.method == "PATCH":
                assert request.content == b"{}"
                return (
                    patch
                    if patch is not None
                    else httpx.Response(200, json=item("UPDATING", "CREATED"))
                )
            latest = next(states, latest)
            return httpx.Response(200, json=latest)

    api.override = handler


async def test_sync_success_and_safe_output(setup):
    client, api, runtime = setup
    install(api, [item(), item("UPDATING", "LOGIN_IN_PROGRESS"), item()])
    server, _ = build_server(client.settings, client)
    _, result = await server.call_tool("sync_item", {"item_id": ITEM})
    assert result["ok"] and result["data"]["success"]
    assert result["data"]["connector"] == {"id": 1, "name": "Synthetic"}
    assert "PRIVATE" not in json.dumps(result)
    assert sum(r.method == "PATCH" for r in api.requests) == 1


@pytest.mark.parametrize("wait", [False, True])
async def test_existing_execution(setup, wait):
    _, api, runtime = setup
    install(api, [item("UPDATING", "CREATED"), item()])
    result = await runtime.invoke("sync_item", item_id=ITEM, wait=wait)
    assert result.data["success"] == wait
    assert result.data["inProgress"] != wait
    assert not any(r.method == "PATCH" for r in api.requests)


@pytest.mark.parametrize("status", ["LOGIN_ERROR", "INVALID_CREDENTIALS", "WAITING_USER_INPUT"])
async def test_requires_action_no_patch(setup, status):
    _, api, runtime = setup
    install(api, [item(status, status)])
    result = await runtime.invoke("sync_item", item_id=ITEM)
    assert result.data["requiresUserAction"] and not result.data["inProgress"]
    assert not any(r.method == "PATCH" for r in api.requests)


@pytest.mark.parametrize(
    "status,execution",
    [
        ("OUTDATED", "ERROR"),
        ("UPDATED", "PARTIAL_SUCCESS"),
        ("WAITING_USER_INPUT", "WAITING_USER_INPUT"),
    ],
)
async def test_terminal_results(setup, status, execution):
    _, api, runtime = setup
    install(api, [item(), item(status, execution)])
    result = await runtime.invoke("sync_item", item_id=ITEM)
    assert not result.data["success"] and not result.data["inProgress"]


async def test_outdated_can_be_explicitly_updated(setup):
    _, api, runtime = setup
    install(api, [item("OUTDATED", "ERROR"), item()])
    result = await runtime.invoke("sync_item", item_id=ITEM)
    assert result.data["success"]


async def test_timeout_is_in_progress(setup):
    client, api, runtime = setup
    client.settings.pluggy_sync_poll_interval_seconds = 0.3
    install(api, [item("UPDATING", "CREATED")])
    result = await runtime.invoke("sync_item", item_id=ITEM, timeout_seconds=1)
    assert result.ok and result.data["inProgress"] and result.data["timedOut"]
    assert len(api.requests) < 8


@pytest.mark.parametrize(
    "code",
    [
        "CLIENT_IS_UPDATING_BEFORE_ALLOWED_FREQUENCY",
        "CONNECTOR_OFFLINE",
        "SANDBOX_CLIENT_ITEM_UPDATE_NOT_ALLOWED",
        "CLIENT_HAS_ITEM_UPDATES_DISABLED",
        "LAST_EXECUTION_HAD_LOGIN_ERROR",
    ],
)
async def test_explicit_errors_preserved(setup, code):
    _, api, runtime = setup
    install(
        api,
        [item()],
        httpx.Response(403, json={"code": code, "message": "PRIVATE", "frequency": 24}),
    )
    result = await runtime.invoke("sync_item", item_id=ITEM)
    assert result.data["error"]["code"] == code
    assert result.data["lastUpdatedAt"]
    assert result.data["nextAllowedUpdateAt"] == "2026-09-16T12:00:00+00:00"
    assert sum(r.method == "PATCH" for r in api.requests) == 1
    assert "PRIVATE" not in result.model_dump_json()


@pytest.mark.parametrize("code", ["ITEM_ALREADY_UPDATING", "ITEM_IS_ALREADY_UPDATING"])
async def test_race_already_updating(setup, code):
    _, api, runtime = setup
    install(api, [item(), item()], httpx.Response(409, json={"code": code}))
    result = await runtime.invoke("sync_item", item_id=ITEM)
    assert result.data["success"]
    assert sum(r.method == "PATCH" for r in api.requests) == 1


@pytest.mark.parametrize("status,attempts", [(401, 2), (403, 1), (429, 3), (503, 1)])
async def test_patch_retry_boundaries(setup, status, attempts):
    _, api, runtime = setup
    install(api, [item()], httpx.Response(status, headers={"Retry-After": "0"}))
    result = await runtime.invoke("sync_item", item_id=ITEM)
    assert not result.data["success"]
    assert sum(r.method == "PATCH" for r in api.requests) == attempts


async def test_retry_after_too_long_preserved(setup):
    _, api, runtime = setup
    install(api, [item()], httpx.Response(429, headers={"Retry-After": "3600"}))
    result = await runtime.invoke("sync_item", item_id=ITEM)
    assert result.data["error"]["retryAfterSeconds"] == 3600
    assert sum(r.method == "PATCH" for r in api.requests) == 1


async def test_invalid_missing_item_and_not_found(setup):
    _, api, runtime = setup
    for identifier in [None, "../../auth"]:
        result = await runtime.invoke("sync_item", item_id=identifier)
        assert result.error["code"] == "INVALID_ARGUMENT"
    assert not api.requests
    result = await runtime.invoke("sync_item", item_id=FOREIGN)
    assert result.error["code"] == "NOT_FOUND"
    assert not any(r.method == "PATCH" for r in api.requests)


async def test_one_client_multiple_items_and_auth_retry():
    requests = []
    keys = 0

    async def handler(request):
        nonlocal keys
        requests.append(request)
        if request.url.path == "/auth":
            keys += 1
            return httpx.Response(200, json={"apiKey": str(keys)})
        if request.headers["X-API-KEY"] == "1":
            return httpx.Response(401)
        return httpx.Response(200, json=item(identifier=request.url.path.split("/")[-1]))

    client = PluggyClient(settings(), httpx.MockTransport(handler))
    try:
        runtime = Runtime(client.settings, client)
        for identifier in [ITEM, FOREIGN]:
            result = await runtime.invoke("get_item", item_id=identifier)
            assert result.data["itemId"] == identifier
        assert keys == 2
        assert not any(r.method == "PATCH" for r in requests)
    finally:
        await client.close()


async def test_patch_network_timeout_never_retried(setup):
    _, api, runtime = setup

    async def handler(request):
        if request.method == "PATCH":
            raise httpx.ReadTimeout("PRIVATE")

    api.override = handler
    result = await runtime.invoke("sync_item", item_id=ITEM)
    assert result.data["inProgress"]
    assert sum(r.method == "PATCH" for r in api.requests) == 1


async def test_concurrent_sync_only_one_patch(setup):
    _, api, runtime = setup
    running = False

    async def handler(request):
        nonlocal running
        if request.url.path.startswith("/items/"):
            if request.method == "PATCH":
                await asyncio.sleep(0.01)
                running = True
            return httpx.Response(200, json=item("UPDATING", "CREATED") if running else item())

    api.override = handler
    await asyncio.gather(*(runtime.invoke("sync_item", item_id=ITEM, wait=False) for _ in range(5)))
    assert sum(r.method == "PATCH" for r in api.requests) == 1


async def test_invalid_timeout_before_network(setup):
    _, api, runtime = setup
    for timeout in [0, -1, True, 3601]:
        result = await runtime.invoke("sync_item", item_id=ITEM, timeout_seconds=timeout)
        assert result.error["code"] == "INVALID_ARGUMENT"
    assert not api.requests


async def test_poll_failure_preserves_running_state(setup):
    _, api, runtime = setup
    calls = 0

    async def handler(request):
        nonlocal calls
        if request.url.path.startswith("/items/"):
            calls += 1
            if calls > 1:
                return httpx.Response(403)
            return httpx.Response(200, json=item("UPDATING", "CREATED"))

    api.override = handler
    result = await runtime.invoke("sync_item", item_id=ITEM)
    assert result.data["inProgress"]
    assert result.data["error"]["code"] == "FORBIDDEN"
    assert not any(r.method == "PATCH" for r in api.requests)


async def test_sync_logs_are_sanitized(setup, caplog):
    _, api, runtime = setup
    install(
        api,
        [item()],
        httpx.Response(
            403,
            json={
                "code": "CLIENT_HAS_ITEM_UPDATES_DISABLED",
                "message": "PRIVATE_API_KEY synthetic-secret PRIVATE_PASSWORD",
            },
        ),
    )
    with caplog.at_level("INFO", logger="pluggy.audit"):
        await runtime.invoke("sync_item", item_id=ITEM)
    assert "CLIENT_HAS_ITEM_UPDATES_DISABLED" in caplog.text
    assert "pluggy.item.validated" in caplog.text
    assert not any(s in caplog.text for s in ["PRIVATE", "synthetic-secret", ITEM])


async def test_unknown_status_never_mutates(setup):
    _, api, runtime = setup
    install(api, [item("UNKNOWN", "PRIVATE")])
    result = await runtime.invoke("sync_item", item_id=ITEM)
    assert not result.data["success"]
    assert not any(r.method == "PATCH" for r in api.requests)


async def test_wrong_item_response_never_mutates(setup):
    _, api, runtime = setup
    install(api, [item(identifier=FOREIGN)])
    result = await runtime.invoke("sync_item", item_id=ITEM)
    assert result.error["code"] == "UPSTREAM_ERROR"
    assert not any(r.method == "PATCH" for r in api.requests)


def test_only_credentials_required(monkeypatch):
    monkeypatch.delenv("PLUGGY_ITEM_ID", raising=False)
    config = settings()
    assert "pluggy_item_id" not in type(config).model_fields
    assert config.pluggy_sync_timeout_seconds == 120
    assert config.pluggy_sync_poll_interval_seconds == 3


async def test_rate_limit_exceeds_sync_deadline_is_not_running(setup):
    _, api, runtime = setup
    install(api, [item()], httpx.Response(429, headers={"Retry-After": "2"}))
    result = await runtime.invoke("sync_item", item_id=ITEM, timeout_seconds=1)
    assert not result.data["inProgress"]
    assert result.data["error"]["code"] == "RATE_LIMITED"
    assert result.data["error"]["retryAfterSeconds"] == 2
    assert sum(r.method == "PATCH" for r in api.requests) == 1
