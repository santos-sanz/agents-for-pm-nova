import pytest
from pydantic import ValidationError

from hyper_demo.config import Settings


def test_settings_reject_mainnet_urls() -> None:
    with pytest.raises(ValidationError):
        Settings(
            HYPERLIQUID_BASE_URL="https://api.hyperliquid.xyz",
            HYPERLIQUID_WS_URL="wss://api.hyperliquid-testnet.xyz/ws",
        )


def test_settings_reject_testnet_string_in_mainnet_path() -> None:
    with pytest.raises(ValidationError):
        Settings(
            HYPERLIQUID_BASE_URL="https://api.hyperliquid.xyz/hyperliquid-testnet",
            HYPERLIQUID_WS_URL="wss://api.hyperliquid-testnet.xyz/ws",
        )


def test_settings_reject_non_testnet_websocket_host() -> None:
    with pytest.raises(ValidationError):
        Settings(
            HYPERLIQUID_BASE_URL="https://api.hyperliquid-testnet.xyz",
            HYPERLIQUID_WS_URL="wss://api.hyperliquid.xyz/hyperliquid-testnet",
        )


def test_settings_accept_testnet_urls() -> None:
    settings = Settings(
        HYPERLIQUID_BASE_URL="https://api.hyperliquid-testnet.xyz",
        HYPERLIQUID_WS_URL="wss://api.hyperliquid-testnet.xyz/ws",
    )
    assert settings.demo_trading_mode == "testnet"


def test_settings_reject_unknown_paper_market_url() -> None:
    with pytest.raises(ValidationError):
        Settings(PAPER_MARKET_BASE_URL="https://example.com")
