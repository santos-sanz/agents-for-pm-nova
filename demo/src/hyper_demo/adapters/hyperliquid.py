from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any

from hyper_demo.config import Settings, get_settings
from hyper_demo.models import OrderRecord, TradePlan, TradeSide, normalize_asset_symbol


class ExecutionBlocked(RuntimeError):
    pass


MAINNET_CONFIRMATION_PHRASE = "CONFIRM MAINNET ORDER"


@dataclass(frozen=True)
class PreparedOrder:
    coin: str
    is_buy: bool
    size: float
    entry_price: float
    stop_loss: float | None
    take_profit: float | None


class HyperliquidAdapter:
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

    def execute_plan(
        self,
        plan: TradePlan,
        confirmed: bool,
        confirmation_phrase: str | None = None,
    ) -> OrderRecord:
        self._validate_execution(plan, confirmed, confirmation_phrase)
        prepared = self.prepare_order(plan)
        raw = self._submit_with_sdk(plan, prepared)
        exchange_name = (
            "hyperliquid-mainnet" if self.settings.is_mainnet_mode else "hyperliquid-testnet"
        )
        environment_label = "mainnet" if self.settings.is_mainnet_mode else "testnet"
        return OrderRecord(
            plan_id=plan.id,
            exchange=exchange_name,
            asset=plan.asset,
            side=plan.side,
            size_usdc=plan.size_usdc,
            entry_order_id=_extract_order_id(raw.get("entry")),
            stop_order_id=_extract_order_id(raw.get("stop_loss")),
            take_profit_order_id=_extract_order_id(raw.get("take_profit")),
            raw_response=raw,
            status="submitted",
            message=(
                "Submitted entry, stop-loss, and take-profit orders to "
                f"Hyperliquid {environment_label}."
            ),
        )

    def wallet_state(self) -> dict[str, Any]:
        if not self.settings.hyperliquid_account_address:
            raise ExecutionBlocked("HYPERLIQUID_ACCOUNT_ADDRESS is required for wallet state.")
        payload = {
            "type": "clearinghouseState",
            "user": self.settings.hyperliquid_account_address,
        }
        request = urllib.request.Request(
            f"{self.settings.hyperliquid_base_url}/info",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - network behavior.
            raise ExecutionBlocked(f"Could not fetch Hyperliquid wallet state: {exc}") from exc
        return _summarize_wallet_state(raw, self.settings.hyperliquid_account_address)

    def _validate_execution(
        self,
        plan: TradePlan,
        confirmed: bool,
        confirmation_phrase: str | None,
    ) -> None:
        if self.settings.demo_require_confirmation and not confirmed:
            raise ExecutionBlocked(
                "Explicit confirmation is required before submitting Hyperliquid orders."
            )
        if not self.settings.has_hyperliquid_credentials:
            raise ExecutionBlocked(
                "Hyperliquid credentials are missing. Configure .env.local or use replay mode."
            )
        asset = normalize_asset_symbol(plan.asset)
        if asset not in self.settings.allowed_assets_set:
            raise ExecutionBlocked(
                f"{asset} is not in the runtime allowed assets."
            )
        if plan.size_usdc > self.settings.hyperliquid_max_order_usdc:
            raise ExecutionBlocked(
                "Order size exceeds HYPERLIQUID_MAX_ORDER_USDC "
                f"({self.settings.hyperliquid_max_order_usdc} USDC)."
            )
        if self.settings.is_mainnet_mode:
            if not self.settings.hyperliquid_mainnet_enabled:
                raise ExecutionBlocked(
                    "Mainnet is disabled. Set HYPERLIQUID_MAINNET_ENABLED=true to proceed."
                )
            if confirmation_phrase != MAINNET_CONFIRMATION_PHRASE:
                raise ExecutionBlocked(
                    "Mainnet execution requires confirmation phrase: "
                    f'"{MAINNET_CONFIRMATION_PHRASE}".'
                )

    def _submit_with_sdk(self, plan: TradePlan, prepared: PreparedOrder) -> dict[str, Any]:
        try:
            from eth_account import Account
            from hyperliquid.exchange import Exchange
        except ImportError as exc:  # pragma: no cover - dependency issue, not business logic.
            raise ExecutionBlocked(f"Hyperliquid SDK dependency is not installed: {exc}") from exc

        private_key = self.settings.hyperliquid_api_wallet_private_key
        try:
            account = Account.from_key(private_key.get_secret_value() if private_key else "")
            exchange = Exchange(
                account,
                base_url=self.settings.hyperliquid_base_url,
                account_address=self.settings.hyperliquid_account_address,
            )
        except (TypeError, ValueError) as exc:
            raise ExecutionBlocked(
                "Hyperliquid wallet configuration is invalid. "
                "Check HYPERLIQUID_ACCOUNT_ADDRESS and HYPERLIQUID_API_WALLET_PRIVATE_KEY."
            ) from exc

        if plan.entry_type == "market":
            entry = exchange.market_open(
                prepared.coin,
                prepared.is_buy,
                prepared.size,
                px=prepared.entry_price,
            )
        else:
            entry = exchange.order(
                prepared.coin,
                prepared.is_buy,
                prepared.size,
                prepared.entry_price,
                {"limit": {"tif": "Ioc"}},
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
        ) if prepared.stop_loss else None
        take_profit = (
            exchange.order(
                prepared.coin,
                closing_is_buy,
                prepared.size,
                prepared.take_profit,
                {
                    "trigger": {
                        "triggerPx": str(prepared.take_profit),
                        "isMarket": True,
                        "tpsl": "tp",
                    }
                },
                reduce_only=True,
            )
            if prepared.take_profit
            else None
        )
        return {"entry": entry, "stop_loss": stop, "take_profit": take_profit}


HyperliquidTestnetAdapter = HyperliquidAdapter


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


def _summarize_wallet_state(raw: dict[str, Any], account_address: str) -> dict[str, Any]:
    margin_summary = raw.get("marginSummary", {}) if isinstance(raw, dict) else {}
    asset_positions = raw.get("assetPositions", []) if isinstance(raw, dict) else []
    positions: list[dict[str, Any]] = []
    exposure = 0.0
    for item in asset_positions:
        position = item.get("position", {}) if isinstance(item, dict) else {}
        if not position:
            continue
        size = float(position.get("szi") or 0)
        entry = float(position.get("entryPx") or 0)
        notional = abs(size * entry)
        exposure += notional
        positions.append(
            {
                "asset": position.get("coin"),
                "size": size,
                "entry_price": entry,
                "position_value_usdc": notional,
                "unrealized_pnl_usdc": float(position.get("unrealizedPnl") or 0),
                "leverage": position.get("leverage"),
            }
        )
    return {
        "account_address": account_address,
        "collateral_usdc": float(margin_summary.get("accountValue") or 0),
        "total_margin_used_usdc": float(margin_summary.get("totalMarginUsed") or 0),
        "withdrawable_usdc": float(raw.get("withdrawable") or 0),
        "open_positions": positions,
        "exposure_usdc": round(exposure, 2),
        "raw": raw,
    }
