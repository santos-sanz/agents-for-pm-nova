import pytest
from pydantic import ValidationError

from hyper_demo.config import Settings, runtime_from_settings, settings_for_runtime
from hyper_demo.models import RuntimeSettings


def test_settings_reject_mainnet_urls_in_testnet_mode() -> None:
    with pytest.raises(ValidationError):
        Settings(
            DEMO_TRADING_MODE="testnet",
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
            DEMO_TRADING_MODE="testnet",
            HYPERLIQUID_BASE_URL="https://api.hyperliquid-testnet.xyz",
            HYPERLIQUID_WS_URL="wss://api.hyperliquid.xyz/hyperliquid-testnet",
        )


def test_settings_accept_testnet_urls() -> None:
    settings = Settings(
        DEMO_TRADING_MODE="testnet",
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


def test_settings_reject_unknown_perplexity_url() -> None:
    with pytest.raises(ValidationError):
        Settings(PERPLEXITY_BASE_URL="https://example.com/v1")


def test_settings_reject_perplexity_url_without_v1_path() -> None:
    with pytest.raises(ValidationError):
        Settings(PERPLEXITY_BASE_URL="https://api.perplexity.ai")


def test_hypertracker_credentials_ignore_empty_and_placeholders() -> None:
    assert not Settings(HYPERTRACKER_API_KEY="").has_hypertracker_credentials
    assert not Settings(HYPERTRACKER_API_KEY="replace-me").has_hypertracker_credentials
    assert Settings(HYPERTRACKER_API_KEY="token").has_hypertracker_credentials


def test_perplexity_credentials_ignore_empty_and_placeholders() -> None:
    assert not Settings(PERPLEXITY_API_KEY="").has_perplexity_credentials
    assert not Settings(PERPLEXITY_API_KEY="replace-me").has_perplexity_credentials
    assert Settings(PERPLEXITY_API_KEY="token").has_perplexity_credentials


def test_managed_chat_mcp_servers_include_tool_url_shortcuts() -> None:
    settings = Settings(
        HYPERTRACKER_MCP_SERVER_URL="https://mcp.example.com/hypertracker",
        PERPLEXITY_MCP_SERVER_URL="https://mcp.example.com/perplexity",
    )

    assert settings.managed_chat_mcp_servers == [
        {
            "name": "hypertracker",
            "type": "url",
            "url": "https://mcp.example.com/hypertracker",
        },
        {
            "name": "perplexity",
            "type": "url",
            "url": "https://mcp.example.com/perplexity",
        },
    ]


def test_managed_chat_mcp_servers_reject_non_https_json_urls() -> None:
    settings = Settings(
        ANTHROPIC_CHAT_MCP_SERVERS='[{"name": "perplexity", "url": "http://mcp.example.com"}]',
    )

    with pytest.raises(ValueError, match="MCP server URLs must be HTTPS"):
        _ = settings.managed_chat_mcp_servers


def test_settings_accept_mainnet_guarded_without_enable_flag() -> None:
    settings = Settings(
        DEMO_TRADING_MODE="mainnet_guarded",
        HYPERLIQUID_BASE_URL="https://api.hyperliquid.xyz",
        HYPERLIQUID_WS_URL="wss://api.hyperliquid.xyz/ws",
    )

    assert settings.hyperliquid_environment == "mainnet"
    assert settings.hyperliquid_mainnet_enabled is False


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


def test_runtime_network_defaults_to_prodnet() -> None:
    assert RuntimeSettings().network == "prodnet"


def test_runtime_bootstrap_uses_env_allowed_assets() -> None:
    settings = Settings(
        HYPERLIQUID_ALLOWED_ASSETS="BTC,xyz:SPCX",
        HYPERLIQUID_MAX_ORDER_USDC=42,
    )

    runtime = runtime_from_settings(settings)

    assert runtime.allowed_assets == ["BTC", "xyz:SPCX"]
    assert runtime.watchlist == ["BTC", "xyz:SPCX"]
    assert runtime.max_order_usdc == 42


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
