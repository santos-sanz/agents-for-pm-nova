from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from hyper_demo.models import RuntimeNetwork, RuntimeSettings

TESTNET_HTTP_HOSTS = {"api.hyperliquid-testnet.xyz"}
TESTNET_WS_HOSTS = {"api.hyperliquid-testnet.xyz"}
MAINNET_HTTP_HOSTS = {"api.hyperliquid.xyz"}
MAINNET_WS_HOSTS = {"api.hyperliquid.xyz"}
HYPERTRACKER_HTTP_HOSTS = {"ht-api.coinmarketman.com"}


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
    hypertracker_api_key: SecretStr | None = Field(default=None, alias="HYPERTRACKER_API_KEY")
    hypertracker_base_url: str = Field(
        default="https://ht-api.coinmarketman.com", alias="HYPERTRACKER_BASE_URL"
    )

    hyperliquid_base_url: str = Field(
        default="https://api.hyperliquid-testnet.xyz", alias="HYPERLIQUID_BASE_URL"
    )
    hyperliquid_ws_url: str = Field(
        default="wss://api.hyperliquid-testnet.xyz/ws", alias="HYPERLIQUID_WS_URL"
    )
    hyperliquid_account_address: str | None = Field(
        default=None, alias="HYPERLIQUID_ACCOUNT_ADDRESS"
    )
    hyperliquid_api_wallet_private_key: SecretStr | None = Field(
        default=None, alias="HYPERLIQUID_API_WALLET_PRIVATE_KEY"
    )

    demo_trading_mode: Literal["testnet", "mainnet_guarded"] = Field(
        default="testnet", alias="DEMO_TRADING_MODE"
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
            if not self.hyperliquid_mainnet_enabled:
                raise ValueError(
                    "Mainnet guarded mode requires HYPERLIQUID_MAINNET_ENABLED=true."
                )
        return self

    @property
    def has_anthropic_credentials(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value())

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
    def has_hyperliquid_credentials(self) -> bool:
        key = self.hyperliquid_api_wallet_private_key
        return bool(
            self.hyperliquid_account_address
            and key
            and key.get_secret_value()
            and "replace" not in key.get_secret_value().lower()
        )

    @property
    def hyperliquid_environment(self) -> Literal["testnet", "mainnet"]:
        return "mainnet" if self.demo_trading_mode == "mainnet_guarded" else "testnet"

    @property
    def is_mainnet_mode(self) -> bool:
        return self.hyperliquid_environment == "mainnet"

    @property
    def allowed_assets_set(self) -> set[str]:
        return {
            asset.strip().upper().replace("-PERP", "")
            for asset in self.hyperliquid_allowed_assets.split(",")
            if asset.strip()
        }


def settings_for_runtime(runtime: RuntimeSettings, base: Settings | None = None) -> Settings:
    """Derive exchange URLs from the selected runtime network.

    The UI can select testnet/prodnet, but it cannot inject exchange URLs.
    """

    base = base or get_settings()
    if runtime.network == RuntimeNetwork.prodnet and not base.hyperliquid_mainnet_enabled:
        raise ValueError("Prodnet requires HYPERLIQUID_MAINNET_ENABLED=true.")

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
