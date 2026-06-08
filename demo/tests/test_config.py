import pytest
from pydantic import ValidationError

from hyper_demo.config import Settings, settings_for_runtime
from hyper_demo.models import RuntimeSettings


def test_settings_reject_mainnet_urls_in_testnet_mode() -> None:
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
        HYPERTRACKER_BASE_URL="https://ht-api.coinmarketman.com",
    )
    assert settings.demo_trading_mode == "testnet"


def test_settings_reject_unknown_hypertracker_url() -> None:
    with pytest.raises(ValidationError):
        Settings(HYPERTRACKER_BASE_URL="https://example.com")


def test_settings_reject_non_https_hypertracker_url() -> None:
    with pytest.raises(ValidationError):
        Settings(HYPERTRACKER_BASE_URL="http://ht-api.coinmarketman.com")


def test_hypertracker_credentials_ignore_empty_and_placeholders() -> None:
    assert not Settings(HYPERTRACKER_API_KEY="").has_hypertracker_credentials
    assert not Settings(HYPERTRACKER_API_KEY="replace-me").has_hypertracker_credentials
    assert Settings(HYPERTRACKER_API_KEY="token").has_hypertracker_credentials


def test_settings_reject_mainnet_guarded_without_enable_flag() -> None:
    with pytest.raises(ValidationError):
        Settings(
            DEMO_TRADING_MODE="mainnet_guarded",
            HYPERLIQUID_BASE_URL="https://api.hyperliquid.xyz",
            HYPERLIQUID_WS_URL="wss://api.hyperliquid.xyz/ws",
        )


def test_settings_accept_mainnet_guarded_when_explicitly_enabled() -> None:
    settings = Settings(
        DEMO_TRADING_MODE="mainnet_guarded",
        HYPERLIQUID_MAINNET_ENABLED=True,
        HYPERLIQUID_BASE_URL="https://api.hyperliquid.xyz",
        HYPERLIQUID_WS_URL="wss://api.hyperliquid.xyz/ws",
        HYPERLIQUID_ALLOWED_ASSETS="BTC,ETH",
    )

    assert settings.hyperliquid_environment == "mainnet"
    assert settings.allowed_assets_set == {"BTC", "ETH"}


def test_runtime_derives_testnet_urls() -> None:
    settings = settings_for_runtime(RuntimeSettings(network="testnet"))

    assert settings.demo_trading_mode == "testnet"
    assert settings.hyperliquid_base_url == "https://api.hyperliquid-testnet.xyz"
    assert settings.hyperliquid_ws_url == "wss://api.hyperliquid-testnet.xyz/ws"


def test_runtime_asset_lists_sync_by_default() -> None:
    runtime = RuntimeSettings(
        watchlist=["ETH"],
        allowed_assets=["BTC", "xyz:SPCX"],
    )

    assert runtime.sync_asset_lists is True
    assert runtime.allowed_assets == ["BTC", "xyz:SPCX"]
    assert runtime.watchlist == ["BTC", "xyz:SPCX"]


def test_runtime_asset_lists_can_be_independent() -> None:
    runtime = RuntimeSettings(
        sync_asset_lists=False,
        watchlist=["ETH"],
        allowed_assets=["BTC", "xyz:SPCX"],
    )

    assert runtime.allowed_assets == ["BTC", "xyz:SPCX"]
    assert runtime.watchlist == ["ETH"]


def test_runtime_derives_prodnet_urls_when_enabled() -> None:
    base = Settings(
        HYPERLIQUID_MAINNET_ENABLED=True,
    )
    runtime = RuntimeSettings(network="prodnet", max_order_usdc=25, allowed_assets=["BTC"])

    settings = settings_for_runtime(runtime, base)

    assert settings.demo_trading_mode == "mainnet_guarded"
    assert settings.hyperliquid_base_url == "https://api.hyperliquid.xyz"
    assert settings.hyperliquid_ws_url == "wss://api.hyperliquid.xyz/ws"
    assert settings.hyperliquid_max_order_usdc == 25
    assert settings.allowed_assets_set == {"BTC"}


def test_runtime_derives_prodnet_urls_without_enabling_execution() -> None:
    settings = settings_for_runtime(RuntimeSettings(network="prodnet"), Settings())

    assert settings.demo_trading_mode == "mainnet_guarded"
    assert settings.hyperliquid_base_url == "https://api.hyperliquid.xyz"
    assert settings.hyperliquid_ws_url == "wss://api.hyperliquid.xyz/ws"
    assert settings.hyperliquid_mainnet_enabled is False
