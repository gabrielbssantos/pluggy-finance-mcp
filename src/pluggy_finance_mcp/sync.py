"""Explicit, bounded synchronization. No institution registry or background tasks."""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any
from weakref import WeakValueDictionary

from pluggy_finance_mcp.client.http import PluggyClient
from pluggy_finance_mcp.client.responses import project
from pluggy_finance_mcp.errors import FinanceError
from pluggy_finance_mcp.policy.readonly import resource_id

ACTION = {
    "INVALID_CREDENTIALS",
    "LOGIN_ERROR",
    "LAST_EXECUTION_HAD_LOGIN_ERROR",
    "WAITING_USER_INPUT",
    "CONNECTOR_REQUIRED_PARAMETER_VALIDATION_ERROR",
}
RUNNING = {
    "CREATED",
    "LOGIN_IN_PROGRESS",
    "LOGIN_MFA_IN_PROGRESS",
    "ACCOUNTS_IN_PROGRESS",
    "TRANSACTIONS_IN_PROGRESS",
    "INVESTMENTS_IN_PROGRESS",
}
LOG_STATES = (
    ACTION
    | RUNNING
    | {
        "UPDATING",
        "UPDATED",
        "OUTDATED",
        "SUCCESS",
        "PARTIAL_SUCCESS",
        "ERROR",
        "CONNECTION_ERROR",
        "SITE_NOT_AVAILABLE",
        "CONNECTOR_OFFLINE",
    }
)


def log_state(value: Any) -> str | None:
    return value if isinstance(value, str) and value in LOG_STATES else None


def item_view(item: dict[str, Any]) -> dict[str, Any]:
    return {**project("item", item), "itemId": item["id"]}


def outcome(item: dict[str, Any]) -> dict[str, Any]:
    status, execution = item.get("status"), item.get("executionStatus")
    error = item.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    action = next((v for v in (status, execution, code) if v in ACTION), None)
    running = not action and (
        status == "UPDATING" or (status not in {"UPDATED", "OUTDATED"} and execution in RUNNING)
    )
    success = status == "UPDATED" and execution in {None, "SUCCESS"} and not action
    result = {
        **item_view(item),
        "success": bool(success),
        "inProgress": bool(running),
        "requiresUserAction": bool(action),
    }
    if action:
        result["error"] = FinanceError(action).public()
        result["message"] = result["error"]["message"]
    elif running:
        result["message"] = "A sincronização continua em andamento."
    elif success:
        result["message"] = "Dados sincronizados com sucesso."
    elif status == "UPDATED" and execution == "PARTIAL_SUCCESS":
        result["partialSuccess"] = True
        result["message"] = "Sincronização parcial; alguns produtos podem estar desatualizados."
    else:
        result["error"] = FinanceError(
            "OUTDATED" if status == "OUTDATED" else "UPSTREAM_ERROR"
        ).public()
        result["message"] = result["error"]["message"]
    return result


class PluggySyncService:
    def __init__(self, client: PluggyClient) -> None:
        self.client = client
        # Only active operations retain locks; no persistent institution state.
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    async def get_item(self, item_id: str) -> dict[str, Any]:
        item = await self.client.get_item(item_id)
        self.event("validated", item)
        return item_view(item)

    async def get_sync_status(self, item_id: str) -> dict[str, Any]:
        return outcome(await self.client.get_item(item_id))

    @staticmethod
    def event(event: str, item: dict[str, Any], **fields: Any) -> None:
        logging.getLogger("pluggy.audit").info(
            json.dumps(
                {
                    "event": "pluggy.item.validated"
                    if event == "validated"
                    else "pluggy.sync." + event,
                    "itemId": str(item.get("id", ""))[:8] + "…",
                    "status": log_state(item.get("status")),
                    "executionStatus": log_state(item.get("executionStatus")),
                    **fields,
                }
            )
        )

    async def sync_item(
        self,
        item_id: str,
        wait: bool = True,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        item_id = resource_id(item_id)
        timeout = (
            self.client.settings.pluggy_sync_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 3600:
            raise FinanceError("INVALID_ARGUMENT")
        if not isinstance(wait, bool):
            raise FinanceError("INVALID_ARGUMENT")
        started = time.monotonic()
        item: dict[str, Any] = {"id": item_id}
        submitted = False
        lock = self._locks.setdefault(item_id, asyncio.Lock())
        try:
            async with asyncio.timeout(timeout):
                async with lock:
                    item = await self.client.get_item(item_id)
                    self.event("validated", item)
                    state = outcome(item)
                    if state["requiresUserAction"]:
                        self.event("user_action_required", item)
                        return state
                    if state["inProgress"]:
                        self.event("already_running", item)
                    else:
                        if item.get("status") not in {"UPDATED", "OUTDATED"}:
                            self.event("failed", item, errorCode="UPSTREAM_ERROR")
                            return state
                        submitted = True
                        try:
                            item = await self.client.update_item(
                                item_id, deadline=started + timeout
                            )
                            self.event("started", item)
                        except FinanceError as error:
                            if error.code not in {
                                "ITEM_ALREADY_UPDATING",
                                "ITEM_IS_ALREADY_UPDATING",
                            }:
                                result = {
                                    **item_view(item),
                                    "success": False,
                                    "inProgress": False,
                                    "requiresUserAction": error.code in ACTION,
                                    "error": error.public(),
                                }
                                frequency = error.details.get("minimumUpdateIntervalHours")
                                if frequency and item.get("lastUpdatedAt"):
                                    try:
                                        last = datetime.fromisoformat(
                                            item["lastUpdatedAt"].replace("Z", "+00:00")
                                        )
                                        if last.tzinfo:
                                            result["nextAllowedUpdateAt"] = (
                                                last + timedelta(hours=frequency)
                                            ).isoformat()
                                    except (ValueError, TypeError, OverflowError):
                                        pass
                                if error.code in {"UPSTREAM_TIMEOUT", "UPSTREAM_UNAVAILABLE"}:
                                    result["inProgress"] = True
                                    result["message"] = (
                                        "Resultado do envio incerto; consulte get_sync_status "
                                        "antes de tentar novamente."
                                    )
                                self.event("failed", item, errorCode=error.code)
                                return result
                            item = {**item, "status": "UPDATING", "executionStatus": "CREATED"}
                            self.event("already_running", item)
                while True:
                    state = outcome(item)
                    if not state["inProgress"] or not wait:
                        if state["requiresUserAction"]:
                            event = "user_action_required"
                        elif state["success"]:
                            event = "completed"
                        else:
                            event = "started" if state["inProgress"] else "failed"
                        self.event(event, item, duration=round(time.monotonic() - started, 3))
                        return state
                    await asyncio.sleep(self.client.settings.pluggy_sync_poll_interval_seconds)
                    try:
                        item = await self.client.get_item(item_id)
                    except FinanceError as error:
                        self.event("failed", item, errorCode=error.code)
                        return {
                            **outcome(item),
                            "error": error.public(),
                            "message": "Não foi possível consultar a execução; "
                            "verifique get_sync_status depois.",
                        }
        except TimeoutError:
            if submitted or outcome(item)["inProgress"]:
                self.event("timeout", item)
                return {
                    **item_view(item),
                    "success": False,
                    "inProgress": True,
                    "message": "A sincronização continua em andamento; consulte get_sync_status.",
                    "timedOut": True,
                }
            raise FinanceError("UPSTREAM_TIMEOUT", True) from None
