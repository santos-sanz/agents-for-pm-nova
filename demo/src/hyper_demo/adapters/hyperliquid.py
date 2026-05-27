from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hyper_demo.config import Settings, get_settings
from hyper_demo.models import OrderRecord, TradePlan, TradeSide


class ExecutionBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedOrder:
    coin: str
    is_buy: bool
    size: float
    entry_price: float
    stop_loss: float
    take_profit: float


class HyperliquidTestnetAdapter:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def prepare_order(self, plan: TradePlan) -> PreparedOrder:
        size = plan.size_usdc / plan.entry_price
        return PreparedOrder(
            coin=plan.asset,
            is_buy=plan.side == TradeSide.long,
            size=round(size, 5),
            entry_price=plan.entry_price,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
        )

    def execute_plan(self, plan: TradePlan, confirmed: bool) -> OrderRecord:
        if self.settings.demo_require_confirmation and not confirmed:
            raise ExecutionBlocked(
                "Explicit confirmation is required before submitting testnet orders."
            )
        if self.settings.demo_trading_mode != "testnet":
            raise ExecutionBlocked("Only testnet trading mode is allowed.")
        if not self.settings.has_hyperliquid_credentials:
            raise ExecutionBlocked(
                "Hyperliquid testnet credentials are missing. Configure .env or use replay mode."
            )

        prepared = self.prepare_order(plan)
        raw = self._submit_with_sdk(plan, prepared)
        return OrderRecord(
            plan_id=plan.id,
            asset=plan.asset,
            side=plan.side,
            size_usdc=plan.size_usdc,
            entry_order_id=_extract_order_id(raw.get("entry")),
            stop_order_id=_extract_order_id(raw.get("stop_loss")),
            take_profit_order_id=_extract_order_id(raw.get("take_profit")),
            raw_response=raw,
            status="submitted",
            message="Submitted entry, stop-loss, and take-profit orders to Hyperliquid testnet.",
        )

    def _submit_with_sdk(self, plan: TradePlan, prepared: PreparedOrder) -> dict[str, Any]:
        try:
            from eth_account import Account
            from hyperliquid.exchange import Exchange
        except ImportError as exc:  # pragma: no cover - dependency issue, not business logic.
            raise ExecutionBlocked(f"Hyperliquid SDK dependency is not installed: {exc}") from exc

        private_key = self.settings.hyperliquid_api_wallet_private_key
        account = Account.from_key(private_key.get_secret_value() if private_key else "")
        exchange = Exchange(
            account,
            base_url=self.settings.hyperliquid_base_url,
            account_address=self.settings.hyperliquid_account_address,
        )

        order_type = {"limit": {"tif": "Ioc"}}
        entry = exchange.order(
            prepared.coin,
            prepared.is_buy,
            prepared.size,
            prepared.entry_price,
            order_type,
            reduce_only=False,
        )
        closing_is_buy = not prepared.is_buy
        stop = exchange.order(
            prepared.coin,
            closing_is_buy,
            prepared.size,
            prepared.stop_loss,
            {"trigger": {"triggerPx": str(prepared.stop_loss), "isMarket": True, "tpsl": "sl"}},
            reduce_only=True,
        )
        take_profit = exchange.order(
            prepared.coin,
            closing_is_buy,
            prepared.size,
            prepared.take_profit,
            {"trigger": {"triggerPx": str(prepared.take_profit), "isMarket": True, "tpsl": "tp"}},
            reduce_only=True,
        )
        return {"entry": entry, "stop_loss": stop, "take_profit": take_profit}


def _extract_order_id(response: Any) -> str | None:
    if not isinstance(response, dict):
        return None
    try:
        statuses = response["response"]["data"]["statuses"]
    except (KeyError, TypeError):
        return None
    if not statuses:
        return None
    first = statuses[0]
    if isinstance(first, dict):
        resting = first.get("resting") or first.get("filled")
        if isinstance(resting, dict):
            oid = resting.get("oid")
            return str(oid) if oid is not None else None
    return None
