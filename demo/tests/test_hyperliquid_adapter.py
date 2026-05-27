import pytest
from pydantic import SecretStr

from hyper_demo.adapters.hyperliquid import ExecutionBlocked, HyperliquidTestnetAdapter
from hyper_demo.config import Settings
from hyper_demo.models import TradePlan


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
        HyperliquidTestnetAdapter(settings).execute_plan(plan, confirmed=True)
