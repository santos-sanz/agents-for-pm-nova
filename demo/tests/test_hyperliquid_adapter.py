import pytest
from pydantic import SecretStr

from hyper_demo.adapters.hyperliquid import ExecutionBlocked, HyperliquidAdapter
from hyper_demo.config import Settings
from hyper_demo.models import OrderRecord, TradePlan


def test_execute_plan_reports_malformed_private_key() -> None:
    settings = Settings(
        HYPERLIQUID_ACCOUNT_ADDRESS="0x0000000000000000000000000000000000000000",
        HYPERLIQUID_API_WALLET_PRIVATE_KEY=SecretStr("not-a-private-key"),
    )
    plan = TradePlan(
        asset="BTC",
        side="long",
        size_usdc=100,
        entry_price=100,
        stop_loss=95,
        take_profit=110,
        max_loss_usdc=5,
        rationale="test",
        invalidation_criteria=[],
    )

    with pytest.raises(ExecutionBlocked, match="wallet configuration is invalid"):
        HyperliquidAdapter(settings).execute_plan(plan, confirmed=True)


def test_execute_plan_blocks_size_above_guardrail() -> None:
    settings = Settings(
        HYPERLIQUID_ACCOUNT_ADDRESS="0x0000000000000000000000000000000000000000",
        HYPERLIQUID_API_WALLET_PRIVATE_KEY=SecretStr(
            "0x0000000000000000000000000000000000000000000000000000000000000001"
        ),
        HYPERLIQUID_MAX_ORDER_USDC=50,
    )
    plan = TradePlan(
        asset="BTC",
        side="long",
        size_usdc=100,
        entry_price=100,
        stop_loss=95,
        take_profit=110,
        max_loss_usdc=5,
        rationale="test",
        invalidation_criteria=[],
    )

    with pytest.raises(ExecutionBlocked, match="exceeds HYPERLIQUID_MAX_ORDER_USDC"):
        HyperliquidAdapter(settings).execute_plan(plan, confirmed=True)


def test_execute_plan_blocks_asset_outside_allowlist() -> None:
    settings = Settings(
        HYPERLIQUID_ACCOUNT_ADDRESS="0x0000000000000000000000000000000000000000",
        HYPERLIQUID_API_WALLET_PRIVATE_KEY=SecretStr(
            "0x0000000000000000000000000000000000000000000000000000000000000001"
        ),
        HYPERLIQUID_ALLOWED_ASSETS="BTC",
    )
    plan = TradePlan(
        asset="DOGE",
        side="long",
        size_usdc=25,
        entry_price=100,
        stop_loss=95,
        take_profit=110,
        max_loss_usdc=5,
        rationale="test",
        invalidation_criteria=[],
    )

    with pytest.raises(ExecutionBlocked, match="not in the runtime allowed assets"):
        HyperliquidAdapter(settings).execute_plan(plan, confirmed=True)


def test_execute_plan_allows_mainnet_without_phrase(monkeypatch) -> None:
    settings = Settings(
        DEMO_TRADING_MODE="mainnet_guarded",
        HYPERLIQUID_MAINNET_ENABLED=True,
        HYPERLIQUID_BASE_URL="https://api.hyperliquid.xyz",
        HYPERLIQUID_WS_URL="wss://api.hyperliquid.xyz/ws",
        HYPERLIQUID_ACCOUNT_ADDRESS="0x0000000000000000000000000000000000000000",
        HYPERLIQUID_API_WALLET_PRIVATE_KEY=SecretStr(
            "0x0000000000000000000000000000000000000000000000000000000000000001"
        ),
    )
    plan = TradePlan(
        asset="BTC",
        side="long",
        size_usdc=25,
        entry_price=100,
        stop_loss=95,
        take_profit=110,
        max_loss_usdc=5,
        rationale="test",
        invalidation_criteria=[],
    )

    def fake_submit(self, submitted_plan, prepared):
        assert submitted_plan == plan
        return {"entry": {"response": {"data": {"statuses": [{"resting": {"oid": 123}}]}}}}

    monkeypatch.setattr(HyperliquidAdapter, "_submit_with_sdk", fake_submit)

    order = HyperliquidAdapter(settings).execute_plan(plan, confirmed=True)

    assert isinstance(order, OrderRecord)
    assert order.exchange == "hyperliquid-mainnet"


def test_wallet_state_queries_main_account_address(monkeypatch) -> None:
    main_account = "0x1111111111111111111111111111111111111111"
    settings = Settings(HYPERLIQUID_ACCOUNT_ADDRESS=main_account)
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            import io
            import json

            return io.BytesIO(
                json.dumps(
                    {
                        "marginSummary": {
                            "accountValue": "1000",
                            "totalMarginUsed": "10",
                        },
                        "withdrawable": "900",
                        "assetPositions": [],
                    }
                ).encode("utf-8")
            )

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

    def fake_urlopen(request, timeout):
        import json

        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    wallet = HyperliquidAdapter(settings).wallet_state()

    assert captured["payload"] == {"type": "clearinghouseState", "user": main_account}
    assert wallet["account_address"] == main_account
    assert wallet["collateral_usdc"] == 1000
