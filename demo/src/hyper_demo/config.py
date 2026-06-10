from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from hyper_demo.models import (
    RuntimeNetwork,
    RuntimeSettings,
    normalize_asset_list,
)

TESTNET_HTTP_HOSTS = {"api.hyperliquid-testnet.xyz"}
TESTNET_WS_HOSTS = {"api.hyperliquid-testnet.xyz"}
MAINNET_HTTP_HOSTS = {"api.hyperliquid.xyz"}
MAINNET_WS_HOSTS = {"api.hyperliquid.xyz"}
HYPERTRACKER_HTTP_HOSTS = {"ht-api.coinmarketman.com"}
PERPLEXITY_HTTP_HOSTS = {"api.perplexity.ai"}


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or local .env files."""

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(
        default="claude-haiku-4-5-20251001",
        alias="ANTHROPIC_MODEL",
    )
    anthropic_agent_id: str | None = Field(default=None, alias="ANTHROPIC_AGENT_ID")
    anthropic_environment_id: str | None = Field(default=None, alias="ANTHROPIC_ENVIRONMENT_ID")
    anthropic_chat_model: str | None = Field(default=None, alias="ANTHROPIC_CHAT_MODEL")
    anthropic_chat_auto_bootstrap: bool = Field(
        default=True,
        alias="ANTHROPIC_CHAT_AUTO_BOOTSTRAP",
    )
    anthropic_chat_max_outcome_iterations: int = Field(
        default=5,
        ge=1,
        le=20,
        alias="ANTHROPIC_CHAT_MAX_OUTCOME_ITERATIONS",
    )
    anthropic_chat_vault_ids: str = Field(default="", alias="ANTHROPIC_CHAT_VAULT_IDS")
    anthropic_chat_mcp_servers: str = Field(default="", alias="ANTHROPIC_CHAT_MCP_SERVERS")
    anthropic_chat_enable_dreams: bool = Field(
        default=False,
        alias="ANTHROPIC_CHAT_ENABLE_DREAMS",
    )
    hypertracker_api_key: SecretStr | None = Field(default=None, alias="HYPERTRACKER_API_KEY")
    hypertracker_base_url: str = Field(
        default="https://ht-api.coinmarketman.com", alias="HYPERTRACKER_BASE_URL"
    )
    hypertracker_mcp_server_url: str | None = Field(
        default=None,
        alias="HYPERTRACKER_MCP_SERVER_URL",
    )
    perplexity_api_key: SecretStr | None = Field(default=None, alias="PERPLEXITY_API_KEY")
    perplexity_base_url: str = Field(
        default="https://api.perplexity.ai/v1", alias="PERPLEXITY_BASE_URL"
    )
    perplexity_mcp_server_url: str | None = Field(
        default=None,
        alias="PERPLEXITY_MCP_SERVER_URL",
    )
    perplexity_model: str = Field(default="perplexity/sonar", alias="PERPLEXITY_MODEL")
    privy_app_id: str | None = Field(default=None, alias="PRIVY_APP_ID")
    privy_client_id: str | None = Field(default=None, alias="PRIVY_CLIENT_ID")
    privy_app_secret: SecretStr | None = Field(default=None, alias="PRIVY_APP_SECRET")
    privy_execution_enabled: bool = Field(default=False, alias="PRIVY_EXECUTION_ENABLED")
    privy_external_withdrawal_address: str = Field(
        default="0xcF1D21Cd958C13aC24BA54506464E64AC80B4214",
        alias="PRIVY_EXTERNAL_WITHDRAWAL_ADDRESS",
    )

    hyperliquid_base_url: str = Field(
        default="https://api.hyperliquid.xyz", alias="HYPERLIQUID_BASE_URL"
    )
    hyperliquid_ws_url: str = Field(
        default="wss://api.hyperliquid.xyz/ws", alias="HYPERLIQUID_WS_URL"
    )
    hyperliquid_account_address: str | None = Field(
        default=None, alias="HYPERLIQUID_ACCOUNT_ADDRESS"
    )
    hyperliquid_api_wallet_private_key: SecretStr | None = Field(
        default=None, alias="HYPERLIQUID_API_WALLET_PRIVATE_KEY"
    )

    demo_trading_mode: Literal["testnet", "mainnet_guarded"] = Field(
        default="mainnet_guarded", alias="DEMO_TRADING_MODE"
    )
    demo_require_confirmation: bool = Field(default=True, alias="DEMO_REQUIRE_CONFIRMATION")
    demo_state_dir: Path = Field(default=Path(".demo_state"), alias="DEMO_STATE_DIR")
    hyperliquid_mainnet_enabled: bool = Field(
        default=False, alias="HYPERLIQUID_MAINNET_ENABLED"
    )
    hyperliquid_max_order_usdc: float = Field(
        default=100.0, gt=0, alias="HYPERLIQUID_MAX_ORDER_USDC"
    )
    hyperliquid_allowed_assets: str = Field(
        default="BTC,ETH,SOL", alias="HYPERLIQUID_ALLOWED_ASSETS"
    )

    @field_validator("hypertracker_base_url")
    @classmethod
    def require_known_hypertracker_http(cls, value: str) -> str:
        parsed = urlparse(value.rstrip("/"))
        if parsed.scheme != "https" or parsed.hostname not in HYPERTRACKER_HTTP_HOSTS:
            raise ValueError("Only the known HyperTracker HTTP URL is allowed in this demo.")
        return parsed.geturl().rstrip("/")

    @field_validator("perplexity_base_url")
    @classmethod
    def require_known_perplexity_http(cls, value: str) -> str:
        parsed = urlparse(value.rstrip("/"))
        if parsed.scheme != "https" or parsed.hostname not in PERPLEXITY_HTTP_HOSTS:
            raise ValueError("Only the known Perplexity API URL is allowed in this demo.")
        if not parsed.path.rstrip("/").endswith("/v1"):
            raise ValueError("Perplexity base URL must end in /v1.")
        return parsed.geturl().rstrip("/")

    @field_validator("hypertracker_mcp_server_url", "perplexity_mcp_server_url")
    @classmethod
    def require_https_mcp_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        parsed = urlparse(value.rstrip("/"))
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Managed Agents MCP server URLs must be HTTPS URLs.")
        return parsed.geturl().rstrip("/")

    @field_validator("privy_external_withdrawal_address")
    @classmethod
    def require_external_withdrawal_evm_address(cls, value: str) -> str:
        clean = value.strip()
        if len(clean) != 42 or not clean.startswith("0x"):
            raise ValueError("PRIVY_EXTERNAL_WITHDRAWAL_ADDRESS must be a 0x EVM address.")
        if any(char not in "0123456789abcdefABCDEF" for char in clean[2:]):
            raise ValueError("PRIVY_EXTERNAL_WITHDRAWAL_ADDRESS must be a 0x EVM address.")
        return clean

    @field_validator("hyperliquid_base_url")
    @classmethod
    def require_known_hyperliquid_http(cls, value: str) -> str:
        parsed = urlparse(value.rstrip("/"))
        allowed_hosts = TESTNET_HTTP_HOSTS | MAINNET_HTTP_HOSTS
        if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
            raise ValueError("Only known Hyperliquid HTTP URLs are allowed in this demo.")
        return parsed.geturl().rstrip("/")

    @field_validator("hyperliquid_ws_url")
    @classmethod
    def require_known_hyperliquid_ws(cls, value: str) -> str:
        parsed = urlparse(value.rstrip("/"))
        if parsed.scheme != "wss" or parsed.hostname not in TESTNET_WS_HOSTS | MAINNET_WS_HOSTS:
            raise ValueError("Only known Hyperliquid websocket URLs are allowed in this demo.")
        return parsed.geturl().rstrip("/")

    @model_validator(mode="after")
    def validate_hyperliquid_environment(self) -> Settings:
        http_host = urlparse(self.hyperliquid_base_url).hostname
        ws_host = urlparse(self.hyperliquid_ws_url).hostname
        if self.demo_trading_mode == "testnet":
            if http_host not in TESTNET_HTTP_HOSTS or ws_host not in TESTNET_WS_HOSTS:
                raise ValueError("Testnet mode requires Hyperliquid testnet HTTP and WS URLs.")
        if self.demo_trading_mode == "mainnet_guarded":
            if http_host not in MAINNET_HTTP_HOSTS or ws_host not in MAINNET_WS_HOSTS:
                raise ValueError(
                    "Mainnet guarded mode requires Hyperliquid mainnet HTTP and WS URLs."
                )
        return self

    @property
    def has_anthropic_credentials(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value())

    @property
    def managed_chat_model(self) -> str:
        return self.anthropic_chat_model or self.anthropic_model

    @property
    def managed_chat_vault_ids(self) -> list[str]:
        return [item.strip() for item in self.anthropic_chat_vault_ids.split(",") if item.strip()]

    @property
    def managed_chat_mcp_servers(self) -> list[dict[str, Any]]:
        raw = self.anthropic_chat_mcp_servers.strip()
        servers: list[dict[str, Any]] = []
        if not raw:
            parsed = []
        else:
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                raise ValueError("ANTHROPIC_CHAT_MCP_SERVERS must be a JSON array.")
        for item in parsed:
            if not isinstance(item, dict):
                raise ValueError("Each MCP server must be an object.")
            name = str(item.get("name") or "").strip()
            url = str(item.get("url") or "").strip()
            if not name or not url:
                raise ValueError("Each MCP server requires name and url.")
            servers.append({"name": name, "type": "url", "url": _normalize_mcp_url(url)})
        for name, url in (
            ("hypertracker", self.hypertracker_mcp_server_url),
            ("perplexity", self.perplexity_mcp_server_url),
        ):
            if url and not _has_mcp_server(name, url, servers):
                servers.append({"name": name, "type": "url", "url": url})
        return servers

    @property
    def has_hypertracker_credentials(self) -> bool:
        key = self.hypertracker_api_key
        return bool(
            key
            and key.get_secret_value()
            and "replace" not in key.get_secret_value().lower()
            and "your_" not in key.get_secret_value().lower()
        )

    @property
    def has_perplexity_credentials(self) -> bool:
        key = self.perplexity_api_key
        return bool(
            key
            and key.get_secret_value()
            and "replace" not in key.get_secret_value().lower()
            and "your_" not in key.get_secret_value().lower()
        )

    @property
    def has_hyperliquid_credentials(self) -> bool:
        key = self.hyperliquid_api_wallet_private_key
        return bool(
            self.hyperliquid_account_address
            and key
            and key.get_secret_value()
            and "replace" not in key.get_secret_value().lower()
        )

    @property
    def has_privy_config(self) -> bool:
        return bool(self.privy_app_id and self.privy_client_id)

    @property
    def has_privy_server_credentials(self) -> bool:
        secret = self.privy_app_secret
        return bool(
            self.privy_app_id
            and secret
            and secret.get_secret_value()
            and "replace" not in secret.get_secret_value().lower()
        )

    @property
    def hyperliquid_environment(self) -> Literal["testnet", "mainnet"]:
        return "mainnet" if self.demo_trading_mode == "mainnet_guarded" else "testnet"

    @property
    def is_mainnet_mode(self) -> bool:
        return self.hyperliquid_environment == "mainnet"

    @property
    def allowed_assets_set(self) -> set[str]:
        return set(self.allowed_assets_list)

    @property
    def allowed_assets_list(self) -> list[str]:
        return normalize_asset_list(self.hyperliquid_allowed_assets.split(","))


def runtime_from_settings(settings: Settings | None = None) -> RuntimeSettings:
    """Create the first browser runtime from env settings.

    After this bootstrap, the persisted runtime is the source of truth for the
    browser app's allowlist and watchlist.
    """

    settings = settings or get_settings()
    allowed_assets = settings.allowed_assets_list or ["BTC", "ETH", "SOL", "HYPE"]
    return RuntimeSettings(
        max_order_usdc=settings.hyperliquid_max_order_usdc,
        allowed_assets=allowed_assets,
        watchlist=allowed_assets,
        sync_asset_lists=True,
    )


def settings_for_runtime(runtime: RuntimeSettings, base: Settings | None = None) -> Settings:
    """Derive exchange URLs from the selected runtime network.

    The UI can select testnet/prodnet, but it cannot inject exchange URLs.
    Mainnet execution is still gated by HYPERLIQUID_MAINNET_ENABLED in the
    execution adapters.
    """

    base = base or get_settings()
    if runtime.network == RuntimeNetwork.prodnet:
        return base.model_copy(
            update={
                "demo_trading_mode": "mainnet_guarded",
                "hyperliquid_base_url": "https://api.hyperliquid.xyz",
                "hyperliquid_ws_url": "wss://api.hyperliquid.xyz/ws",
                "hyperliquid_max_order_usdc": runtime.max_order_usdc,
                "hyperliquid_allowed_assets": ",".join(runtime.allowed_assets),
            }
        )
    return base.model_copy(
        update={
            "demo_trading_mode": "testnet",
            "hyperliquid_base_url": "https://api.hyperliquid-testnet.xyz",
            "hyperliquid_ws_url": "wss://api.hyperliquid-testnet.xyz/ws",
            "hyperliquid_max_order_usdc": runtime.max_order_usdc,
            "hyperliquid_allowed_assets": ",".join(runtime.allowed_assets),
        }
    )


def _has_mcp_server(name: str, url: str, servers: list[dict[str, Any]]) -> bool:
    normalized_name = name.lower()
    normalized_url = url.rstrip("/")
    return any(
        str(server.get("name", "")).lower() == normalized_name
        or str(server.get("url", "")).rstrip("/") == normalized_url
        for server in servers
    )


def _normalize_mcp_url(value: str) -> str:
    parsed = urlparse(value.rstrip("/"))
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Managed Agents MCP server URLs must be HTTPS URLs.")
    return parsed.geturl().rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
