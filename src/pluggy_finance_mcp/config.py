from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
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
    mcp_auth_mode: Literal["local_process", "bearer"] = "local_process"
    mcp_bearer_token: SecretStr | None = None
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
        if self.mcp_transport == "streamable-http":
            token = self.mcp_bearer_token
            if self.mcp_auth_mode != "bearer" or not token or len(token.get_secret_value()) < 32:
                raise ValueError(
                    "HTTP requires bearer authentication with a token of 32+ characters"
                )
        if not self.hosts or any("*" in host or "/" in host for host in self.hosts):
            raise ValueError("Explicit allowed hosts required")
        return self

    @property
    def hosts(self) -> list[str]:
        return [host.strip() for host in self.mcp_allowed_hosts.split(",") if host.strip()]
