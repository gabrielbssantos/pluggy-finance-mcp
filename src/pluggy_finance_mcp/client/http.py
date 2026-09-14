import asyncio
import random
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
import simplejson

from pluggy_finance_mcp.config import Settings
from pluggy_finance_mcp.errors import FinanceError, upstream_error
from pluggy_finance_mcp.policy.readonly import resolve


async def read_json(
    client: httpx.AsyncClient, method: str, url: str, max_bytes: int, **kwargs: Any
) -> tuple[int, httpx.Headers, dict[str, Any]]:
    async with client.stream(method, url, follow_redirects=False, **kwargs) as response:
        if response.status_code != 200:
            return response.status_code, response.headers, {}
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > max_bytes:
                raise FinanceError("UPSTREAM_ERROR")
        try:
            result = simplejson.loads(bytes(body), use_decimal=True)
        except (ValueError, UnicodeDecodeError):
            raise FinanceError("UPSTREAM_ERROR") from None
        if not isinstance(result, dict):
            raise FinanceError("UPSTREAM_ERROR")
        return response.status_code, response.headers, result


class PluggyAuth:
    """Only component permitted to POST; endpoint and payload are fixed."""

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
            self._key = key
            self._expires = (
                time.monotonic() + 7200 - self.settings.pluggy_api_key_refresh_margin_seconds
            )
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
        renewed = False
        for attempt in range(3):
            try:
                key = await self.auth.key()
                status, headers, data = await read_json(
                    self.http,
                    "GET",
                    "https://api.pluggy.ai" + path,
                    self.settings.max_response_bytes,
                    params=query,
                    headers={"X-API-KEY": key},
                )
                if status == 200:
                    return data
                if status == 401 and not renewed and attempt < 2:
                    await self.auth.key(rejected_key=key)
                    renewed = True
                    continue
                error = upstream_error(status)
                if not error.retryable or attempt == 2:
                    raise error
                delay = retry_delay(headers.get("Retry-After"), attempt)
            except httpx.TimeoutException:
                if attempt == 2:
                    raise FinanceError("UPSTREAM_TIMEOUT", True) from None
                delay = retry_delay(None, attempt)
            except httpx.RequestError:
                if attempt == 2:
                    raise FinanceError("UPSTREAM_UNAVAILABLE", True) from None
                delay = retry_delay(None, attempt)
            await asyncio.sleep(delay)
        raise FinanceError("UPSTREAM_ERROR")


def retry_delay(value: str | None, attempt: int) -> float:
    if value:
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                return max(0.0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
    return float(2**attempt) + random.uniform(0, 0.25)
