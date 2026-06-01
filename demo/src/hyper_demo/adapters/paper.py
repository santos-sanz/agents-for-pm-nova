from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hyper_demo.config import Settings, get_settings
from hyper_demo.models import OrderRecord, TradePlan, TradeSide, new_id
from hyper_demo.services.market import CoinbasePublicMarketDataClient, MarketPrice


class PaperExecutionBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class PaperFill:
    fill_price: float
    size_base: float
    notional_usdc: float
    slippage_bps: float


class PaperTradingAdapter:
    """Credential-free simulated execution backed by public Coinbase market data."""

    def __init__(
        self,
        settings: Settings | None = None,
        market: CoinbasePublicMarketDataClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.market = market or CoinbasePublicMarketDataClient(self.settings)

    def execute_plan(self, plan: TradePlan, confirmed: bool) -> OrderRecord:
        if self.settings.demo_require_confirmation and not confirmed:
            raise PaperExecutionBlocked(
                "Explicit confirmation is required before starting a paper trading run."
            )

        price = self.market.mark_price(plan.asset)
        fill = self._fill(plan, price)
        debug_trace = self._debug_trace(plan, price, fill)
        return OrderRecord(
            plan_id=plan.id,
            exchange="paper-coinbase",
            asset=plan.asset,
            side=plan.side,
            size_usdc=plan.size_usdc,
            entry_order_id=new_id("paper_entry"),
            stop_order_id=new_id("paper_stop"),
            take_profit_order_id=new_id("paper_tp"),
            raw_response={
                "mode": "paper",
                "market_data": {
                    "provider": "coinbase_exchange_public",
                    "base_url": self.settings.paper_market_base_url,
                    "product_id": self.market.product_id(plan.asset),
                    "source": price.source,
                    "mark_price": price.mark_price,
                },
                "fill": fill.__dict__,
                "plan": plan.model_dump(mode="json"),
                "debug_trace": debug_trace,
            },
            status="simulated",
            message=(
                "Simulated paper trade using Coinbase Exchange public ticker data. "
                "No live order was submitted."
            ),
        )

    def _fill(self, plan: TradePlan, price: MarketPrice) -> PaperFill:
        direction = 1 if plan.side == TradeSide.long else -1
        slippage_bps = 2.0
        fill_price = price.mark_price * (1 + direction * slippage_bps / 10_000)
        size_base = plan.size_usdc / fill_price
        return PaperFill(
            fill_price=round(fill_price, 4),
            size_base=round(size_base, 8),
            notional_usdc=round(plan.size_usdc, 2),
            slippage_bps=slippage_bps,
        )

    def _debug_trace(
        self,
        plan: TradePlan,
        price: MarketPrice,
        fill: PaperFill,
    ) -> list[dict[str, Any]]:
        risk_distance = abs(fill.fill_price - plan.stop_loss)
        per_unit_risk = risk_distance * fill.size_base
        return [
            {
                "step": "market_data",
                "message": "Fetched a public ticker price for simulated execution.",
                "asset": plan.asset,
                "source": price.source,
                "mark_price": price.mark_price,
            },
            {
                "step": "entry_fill",
                "message": "Applied deterministic paper slippage to make fills inspectable.",
                "side": plan.side.value,
                "fill_price": fill.fill_price,
                "size_base": fill.size_base,
                "slippage_bps": fill.slippage_bps,
            },
            {
                "step": "risk_bracket",
                "message": "Registered virtual stop-loss and take-profit orders.",
                "stop_loss": plan.stop_loss,
                "take_profit": plan.take_profit,
                "estimated_loss_usdc": round(per_unit_risk, 2),
                "declared_max_loss_usdc": plan.max_loss_usdc,
            },
        ]
