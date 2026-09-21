from typing import Literal, Self

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    pluggy_client_id: SecretStr
    pluggy_client_secret: SecretStr
    pluggy_sync_poll_interval_seconds: float = Field(default=3, gt=0, le=60)
    pluggy_sync_timeout_seconds: int = Field(default=120, ge=1, le=3600)
    pluggy_base_url: Literal["https://api.pluggy.ai"] = "https://api.pluggy.ai"
    pluggy_api_key_refresh_margin_seconds: int = Field(default=900, ge=0, lt=7200)
    pluggy_http_timeout_seconds: float = Field(default=45, gt=0, le=45)
    mcp_transport: Literal["stdio", "streamable-http"] = "stdio"
    mcp_auth_mode: Literal["local_process", "oauth"] = "local_process"
    mcp_public_url: AnyHttpUrl | None = None
    mcp_oauth_issuer_url: AnyHttpUrl | None = None
    mcp_oauth_allowed_subject: str | None = None
    mcp_oauth_allowed_client_ids: str = ""
    mcp_oauth_scope: str = "pluggy:access"
    mcp_oauth_signing_algorithm: Literal["RS256", "ES256"] = "RS256"
    mcp_allowed_hosts: str = "localhost,127.0.0.1"
    semantic_max_pages: int = Field(default=10, ge=1, le=10)
    semantic_max_records: int = Field(default=2000, ge=1, le=2000)
    max_response_bytes: int = Field(default=2_000_000, ge=1024, le=10_000_000)
    port: int = Field(default=8080, ge=1, le=65535)
    enable_identity_tool: Literal[False] = False
    log_pii: Literal[False] = False
    k_service: str | None = None

    @model_validator(mode="after")
    def secure_configuration(self) -> Self:
        for secret in (self.pluggy_client_id, self.pluggy_client_secret):
            if not secret.get_secret_value().strip():
                raise ValueError("Required credential missing")
        if self.k_service and self.mcp_transport != "streamable-http":
            raise ValueError("Cloud Run requires HTTP")
        if not self.hosts or any("*" in host or "/" in host for host in self.hosts):
            raise ValueError("Explicit allowed hosts required")
        if self.mcp_transport == "stdio":
            if self.mcp_auth_mode != "local_process":
                raise ValueError("stdio requires local_process authentication")
            return self
        if self.mcp_auth_mode != "oauth":
            raise ValueError("HTTP requires OAuth authentication")
        if not self.mcp_public_url or not self.mcp_oauth_issuer_url:
            raise ValueError("HTTP requires public and issuer URLs")
        for name, url in (
            ("public", self.mcp_public_url),
            ("issuer", self.mcp_oauth_issuer_url),
        ):
            if url.scheme != "https" or url.query or url.fragment or url.username or url.password:
                raise ValueError(
                    f"OAuth {name} URL must be credential-free HTTPS without query or fragment"
                )
        if self.mcp_public_url.path != "/mcp":
            raise ValueError("MCP public URL must end exactly in /mcp")
        if self.mcp_public_url.host not in self.hosts:
            raise ValueError("MCP public URL host must be explicitly allowed")
        if (
            not self.mcp_oauth_allowed_subject
            or self.mcp_oauth_allowed_subject != self.mcp_oauth_allowed_subject.strip()
        ):
            raise ValueError("HTTP requires one allowed OAuth subject")
        if "*" in self.mcp_oauth_allowed_client_ids or not self.oauth_client_ids:
            raise ValueError("HTTP requires allowed OAuth client IDs")
        if not self.mcp_oauth_scope or not all(
            ord(char) == 0x21 or 0x23 <= ord(char) <= 0x5B or 0x5D <= ord(char) <= 0x7E
            for char in self.mcp_oauth_scope
        ):
            raise ValueError("OAuth scope must be one non-empty scope token")
        return self

    @property
    def hosts(self) -> list[str]:
        return [host.strip() for host in self.mcp_allowed_hosts.split(",") if host.strip()]

    @property
    def oauth_client_ids(self) -> list[str]:
        values = [value.strip() for value in self.mcp_oauth_allowed_client_ids.split(",")]
        return [value for value in values if value and "*" not in value]
