import pytest

from hyper_demo.adapters.paper import PaperExecutionBlocked, PaperTradingAdapter
from hyper_demo.config import Settings
from hyper_demo.models import TradePlan
from hyper_demo.services.market import MarketPrice


class StaticPaperMarket:
    def product_id(self, asset: str) -> str:
        return f"{asset}-USD"

    def mark_price(self, asset: str) -> MarketPrice:
        return MarketPrice(asset=asset, mark_price=100.0, source="test")


def make_plan(side: str = "long") -> TradePlan:
    return TradePlan(
        asset="BTC",
        side=side,
        size_usdc=100,
        entry_price=100,
        stop_loss=95 if side == "long" else 105,
        take_profit=110 if side == "long" else 90,
        max_loss_usdc=5,
        rationale="test",
        invalidation_criteria=[],
    )


def test_paper_trading_requires_confirmation() -> None:
    adapter = PaperTradingAdapter(Settings(), StaticPaperMarket())

    with pytest.raises(PaperExecutionBlocked, match="confirmation"):
        adapter.execute_plan(make_plan(), confirmed=False)


def test_paper_trading_records_debug_trace() -> None:
    adapter = PaperTradingAdapter(Settings(), StaticPaperMarket())

    order = adapter.execute_plan(make_plan(), confirmed=True)

    assert order.exchange == "paper-coinbase"
    assert order.status == "simulated"
    assert order.raw_response["fill"]["fill_price"] == 100.02
    assert [step["step"] for step in order.raw_response["debug_trace"]] == [
        "market_data",
        "entry_fill",
        "risk_bracket",
    ]
