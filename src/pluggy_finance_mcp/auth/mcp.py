import asyncio
import secrets
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
import jwt
from jwt import PyJWK, PyJWTError
from mcp.server.auth.provider import AccessToken
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from pluggy_finance_mcp.config import Settings

_DEFAULT_JWKS_TTL_SECONDS = 300
_MIN_JWKS_TTL_SECONDS = 60
_MAX_JWKS_TTL_SECONDS = 3600
_UNKNOWN_KID_REFRESH_SECONDS = 30
_FAILED_REFRESH_BACKOFF_SECONDS = 5
_MAX_AUTH_RESPONSE_BYTES = 262_144


class OidcJwtVerifier:
    """Validate access-token JWTs issued for this single-user MCP resource."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        if not settings.mcp_public_url or not settings.mcp_oauth_issuer_url:
            raise ValueError("OAuth verifier requires remote OAuth settings")
        self.issuer = str(settings.mcp_oauth_issuer_url)
        self.resource = str(settings.mcp_public_url)
        self.subject = settings.mcp_oauth_allowed_subject or ""
        self.client_ids = tuple(settings.oauth_client_ids)
        self.scope = settings.mcp_oauth_scope
        self.algorithm = settings.mcp_oauth_signing_algorithm
        self._http = http or httpx.AsyncClient(timeout=5, follow_redirects=False)
        self._owns_http = http is None
        self._keys: dict[str, Mapping[str, Any]] = {}
        self._keys_expires_at = 0.0
        self._last_unknown_kid_refresh = 0.0
        self._refresh_not_before = 0.0
        self._jwks_uri: str | None = None
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("jku") is not None or header.get("x5u") is not None:
                return None
            if header.get("alg") != self.algorithm:
                return None
            kid = header.get("kid")
            if not isinstance(kid, str) or not kid:
                return None
            jwk = await self._key_for(kid)
            if jwk is None:
                return None
            key = PyJWK.from_dict(dict(jwk), algorithm=self.algorithm).key
            if self.algorithm == "RS256" and getattr(key, "key_size", 0) < 2048:
                return None
            claims = jwt.decode(
                token,
                key=key,
                algorithms=[self.algorithm],
                audience=self.resource,
                issuer=self.issuer,
                leeway=30,
                options={"require": ["iss", "aud", "exp", "sub"]},
            )
            subject = claims.get("sub")
            if not isinstance(subject, str) or not secrets.compare_digest(subject, self.subject):
                return None
            client_id = claims.get("azp") or claims.get("client_id")
            if not isinstance(client_id, str) or not any(
                secrets.compare_digest(client_id, allowed) for allowed in self.client_ids
            ):
                return None
            scopes = self._scopes(claims)
            if self.scope not in scopes:
                return None
            expires_at = claims.get("exp")
            if not isinstance(expires_at, int):
                return None
            return AccessToken(
                token=token,
                client_id=client_id,
                scopes=scopes,
                expires_at=expires_at,
                resource=self.resource,
                subject=subject,
                claims={"iss": self.issuer},
            )
        except (PyJWTError, ValueError, TypeError, httpx.HTTPError):
            return None

    @staticmethod
    def _scopes(claims: Mapping[str, Any]) -> list[str]:
        values: list[str] = []
        scope = claims.get("scope")
        if isinstance(scope, str):
            values.extend(scope.split())
        scp = claims.get("scp")
        if isinstance(scp, str):
            values.extend(scp.split())
        elif isinstance(scp, list):
            values.extend(value for value in scp if isinstance(value, str))
        return list(dict.fromkeys(values))

    async def _key_for(self, kid: str) -> Mapping[str, Any] | None:
        now = time.monotonic()
        if now < self._keys_expires_at and kid in self._keys:
            return self._keys[kid]
        async with self._lock:
            now = time.monotonic()
            if now < self._keys_expires_at and kid in self._keys:
                return self._keys[kid]
            expired = now >= self._keys_expires_at
            if expired and now < self._refresh_not_before:
                return None
            may_refresh_unknown = (
                now - self._last_unknown_kid_refresh >= _UNKNOWN_KID_REFRESH_SECONDS
            )
            if expired or may_refresh_unknown:
                if not expired:
                    self._last_unknown_kid_refresh = now
                try:
                    await self._refresh_keys()
                except (ValueError, TypeError, httpx.HTTPError):
                    self._refresh_not_before = now + _FAILED_REFRESH_BACKOFF_SECONDS
                    raise
                if kid not in self._keys:
                    self._last_unknown_kid_refresh = now
            return self._keys.get(kid)

    async def _refresh_keys(self) -> None:
        jwks_uri = self._jwks_uri or await self._discover_jwks_uri()
        response = await self._http.get(jwks_uri, headers={"Accept": "application/json"})
        self._ensure_bounded(response)
        response.raise_for_status()
        payload = response.json()
        keys = payload.get("keys") if isinstance(payload, dict) else None
        if not isinstance(keys, list) or not 1 <= len(keys) <= 32:
            raise ValueError("Invalid JWKS")
        parsed: dict[str, Mapping[str, Any]] = {}
        expected_kty = "RSA" if self.algorithm == "RS256" else "EC"
        for key in keys:
            if not isinstance(key, dict):
                continue
            kid = key.get("kid")
            valid_use = key.get("use") in {None, "sig"}
            key_ops = key.get("key_ops")
            valid_ops = key_ops is None or (isinstance(key_ops, list) and "verify" in key_ops)
            valid_algorithm = key.get("alg") in {None, self.algorithm}
            if (
                isinstance(kid, str)
                and kid
                and key.get("kty") == expected_kty
                and (self.algorithm != "ES256" or key.get("crv") == "P-256")
                and valid_use
                and valid_ops
                and valid_algorithm
            ):
                if kid in parsed:
                    raise ValueError("JWKS has duplicate key IDs")
                parsed[kid] = key
        if not parsed:
            raise ValueError("JWKS has no usable keys")
        self._keys = parsed
        self._keys_expires_at = time.monotonic() + self._cache_ttl(response)

    async def _discover_jwks_uri(self) -> str:
        for discovery_url in self._discovery_urls():
            response = await self._http.get(discovery_url, headers={"Accept": "application/json"})
            self._ensure_bounded(response)
            if response.status_code == 404:
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or str(payload.get("issuer", "")) != self.issuer:
                raise ValueError("Discovery issuer mismatch")
            jwks_uri = payload.get("jwks_uri")
            if not isinstance(jwks_uri, str) or not self._safe_https_url(jwks_uri):
                raise ValueError("Invalid JWKS URI")
            self._jwks_uri = jwks_uri
            return jwks_uri
        raise ValueError("OAuth discovery unavailable")

    def _discovery_urls(self) -> tuple[str, str]:
        oidc = self.issuer.rstrip("/") + "/.well-known/openid-configuration"
        parts = urlsplit(self.issuer)
        oauth_path = "/.well-known/oauth-authorization-server" + parts.path.rstrip("/")
        oauth = urlunsplit((parts.scheme, parts.netloc, oauth_path, "", ""))
        return oidc, oauth

    @staticmethod
    def _safe_https_url(value: str) -> bool:
        parts = urlsplit(value)
        return (
            parts.scheme == "https"
            and bool(parts.netloc)
            and not parts.username
            and not parts.password
            and not parts.fragment
        )

    @staticmethod
    def _ensure_bounded(response: httpx.Response) -> None:
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                length = int(content_length)
            except ValueError as error:
                raise ValueError("Invalid OAuth content length") from error
            if length > _MAX_AUTH_RESPONSE_BYTES:
                raise ValueError("OAuth response too large")
        if len(response.content) > _MAX_AUTH_RESPONSE_BYTES:
            raise ValueError("OAuth response too large")

    @staticmethod
    def _cache_ttl(response: httpx.Response) -> int:
        for directive in response.headers.get("cache-control", "").split(","):
            name, _, value = directive.strip().partition("=")
            if name.lower() == "max-age" and value.isdigit():
                return max(_MIN_JWKS_TTL_SECONDS, min(int(value), _MAX_JWKS_TTL_SECONDS))
        return _DEFAULT_JWKS_TTL_SECONDS


class AuthorizationHeaderGuardMiddleware:
    """Reject ambiguous credentials before Starlette normalizes duplicate headers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] == "/mcp":
            values = [value for key, value in scope["headers"] if key.lower() == b"authorization"]
            if len(values) > 1:
                response = JSONResponse({"error": "INVALID_AUTHORIZATION"}, status_code=400)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
