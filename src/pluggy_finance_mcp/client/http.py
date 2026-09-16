import asyncio
import json
import logging
import math
import random
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
import simplejson

from pluggy_finance_mcp.config import Settings
from pluggy_finance_mcp.errors import FinanceError, upstream_error
from pluggy_finance_mcp.policy.readonly import resolve, resource_id


async def read_json(
    client: httpx.AsyncClient, method: str, url: str, max_bytes: int, **kwargs: Any
) -> tuple[int, httpx.Headers, dict[str, Any]]:
    async with client.stream(method, url, follow_redirects=False, **kwargs) as response:
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > max_bytes:
                raise FinanceError("UPSTREAM_ERROR")
        try:
            result = simplejson.loads(bytes(body), use_decimal=True)
        except (ValueError, UnicodeDecodeError):
            if response.status_code != 200:
                return response.status_code, response.headers, {}
            raise FinanceError("UPSTREAM_ERROR") from None
        if not isinstance(result, dict):
            if response.status_code != 200:
                return response.status_code, response.headers, {}
            raise FinanceError("UPSTREAM_ERROR")
        return response.status_code, response.headers, result


class PluggyAuth:
    """Memory-only API key manager; endpoint and payload are fixed."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client
        self._key: str | None = None
        self._expires = 0.0
        self._lock = asyncio.Lock()

    async def key(self, rejected_key: str | None = None) -> str:
        async with self._lock:
            if rejected_key is not None and self._key == rejected_key:
                self._key = None
            if self._key and time.monotonic() < self._expires:
                return self._key
            key = await self.authenticate()
            event = "pluggy.auth.refreshed" if self._expires else "pluggy.auth.created"
            self._key = key
            self._expires = (
                time.monotonic() + 7200 - self.settings.pluggy_api_key_refresh_margin_seconds
            )
            logging.getLogger("pluggy.audit").info(json.dumps({"event": event}))
            return key

    async def authenticate(self) -> str:
        """Generate a key only. Cache lifecycle is managed by key()."""
        try:
            status, _, data = await read_json(
                self.client,
                "POST",
                "https://api.pluggy.ai/auth",
                16384,
                json={
                    "clientId": self.settings.pluggy_client_id.get_secret_value(),
                    "clientSecret": self.settings.pluggy_client_secret.get_secret_value(),
                },
            )
        except httpx.TimeoutException:
            raise FinanceError("UPSTREAM_TIMEOUT", True) from None
        except httpx.RequestError:
            raise FinanceError("UPSTREAM_UNAVAILABLE", True) from None
        if status != 200:
            raise upstream_error(status)
        key = data.get("apiKey")
        if not isinstance(key, str) or not key:
            raise FinanceError("UPSTREAM_ERROR")
        return key


class PluggyClient:
    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.settings = settings
        self.http = httpx.AsyncClient(
            timeout=settings.pluggy_http_timeout_seconds,
            follow_redirects=False,
            transport=transport,
            trust_env=False,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self.auth = PluggyAuth(settings, self.http)

    async def close(self) -> None:
        await self.http.aclose()

    async def get(
        self,
        operation: str,
        identifier: str | None = None,
        params: dict[str, Any] | None = None,
        *,
        method: str = "GET",
    ) -> dict[str, Any]:
        query = {k: v for k, v in (params or {}).items() if v is not None}
        path = resolve(operation, identifier, query, method)
        return await self._request("GET", path, query)

    async def get_item(self, item_id: str) -> dict[str, Any]:
        item_id = resource_id(item_id)
        data = await self.get("item", item_id)
        if data.get("id") != item_id or not isinstance(data.get("status"), str):
            raise FinanceError("UPSTREAM_ERROR")
        return data

    async def update_item(
        self,
        item_id: str,
        *,
        deadline: float | None = None,
    ) -> dict[str, Any]:
        item_id = resource_id(item_id)
        data = await self._request("PATCH", f"/items/{item_id}", deadline=deadline)
        if data.get("id") != item_id or not isinstance(data.get("status"), str):
            raise FinanceError("UPSTREAM_ERROR")
        return data

    async def _request(
        self,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        *,
        deadline: float | None = None,
    ) -> dict[str, Any]:
        renewed = False
        attempt = 0
        while True:
            try:
                key = await self.auth.key()
                status, headers, data = await read_json(
                    self.http,
                    method,
                    "https://api.pluggy.ai" + path,
                    self.settings.max_response_bytes,
                    params=query,
                    headers={"X-API-KEY": key},
                    **({"json": {}} if method == "PATCH" else {}),
                )
                if status == 200:
                    return data
                if status == 401 and not renewed:
                    await self.auth.key(rejected_key=key)
                    renewed = True
                    continue
                error = upstream_error(status, data)
                logging.getLogger("pluggy.audit").info(
                    json.dumps(
                        {
                            "event": "pluggy.http.rejected",
                            "operation": method + " " + path.split("/")[1],
                            "httpStatus": status,
                            "errorCode": error.code,
                            "message": error.public()["message"],
                        }
                    )
                )
                retryable = status == 429 or (method == "GET" and status in {502, 503, 504})
                if status == 429 and headers.get("Retry-After"):
                    error.details["retryAfterSeconds"] = retry_delay(
                        headers["Retry-After"], attempt
                    )
                if not retryable or attempt == 2:
                    raise error
                delay = retry_delay(headers.get("Retry-After"), attempt)
                remaining = deadline - time.monotonic() if deadline is not None else float("inf")
                if delay > self.settings.pluggy_http_timeout_seconds or delay >= remaining:
                    error.details["retryAfterSeconds"] = delay
                    raise error
            except httpx.TimeoutException:
                if method == "PATCH" or attempt == 2:
                    raise FinanceError("UPSTREAM_TIMEOUT", True) from None
                delay = retry_delay(None, attempt)
            except httpx.RequestError:
                if method == "PATCH" or attempt == 2:
                    raise FinanceError("UPSTREAM_UNAVAILABLE", True) from None
                delay = retry_delay(None, attempt)
            await asyncio.sleep(delay)
            attempt += 1


def retry_delay(value: str | None, attempt: int) -> float:
    if value:
        try:
            seconds = float(value)
            if math.isfinite(seconds):
                return max(0.0, seconds)
        except ValueError:
            try:
                return max(0.0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
    return float(2**attempt) + random.uniform(0, 0.25)
