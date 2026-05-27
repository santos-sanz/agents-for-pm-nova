from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    demo_trading_mode: Literal["testnet"] = Field(default="testnet", alias="DEMO_TRADING_MODE")
    demo_require_confirmation: bool = Field(default=True, alias="DEMO_REQUIRE_CONFIRMATION")
    demo_state_dir: Path = Field(default=Path(".demo_state"), alias="DEMO_STATE_DIR")

    @field_validator("hyperliquid_base_url")
    @classmethod
    def require_hyperliquid_testnet_http(cls, value: str) -> str:
        if "hyperliquid-testnet" not in value:
            raise ValueError("Only Hyperliquid testnet HTTP URLs are allowed in this demo.")
        return value.rstrip("/")

    @field_validator("hyperliquid_ws_url")
    @classmethod
    def require_hyperliquid_testnet_ws(cls, value: str) -> str:
        if "hyperliquid-testnet" not in value:
            raise ValueError("Only Hyperliquid testnet websocket URLs are allowed in this demo.")
        return value.rstrip("/")

    @property
    def has_anthropic_credentials(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value())

    @property
    def has_hyperliquid_credentials(self) -> bool:
        key = self.hyperliquid_api_wallet_private_key
        return bool(
            self.hyperliquid_account_address
            and key
            and key.get_secret_value()
            and "replace" not in key.get_secret_value().lower()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
