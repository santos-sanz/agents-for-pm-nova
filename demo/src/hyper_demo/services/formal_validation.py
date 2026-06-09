from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hyper_demo.models import RuntimeSettings, TradePlan, TradeSide, normalize_asset_symbol

HYPERLIQUID_MIN_NOTIONAL_BUFFER_USDC = 0.25
DEFAULT_INTRADAY_MIN_LEVERAGE = 2.0
DEFAULT_MAX_PLANNED_LOSS_USDC = 2.0


@dataclass(frozen=True)
class FormalValidationResult:
    valid: bool
    checks: list[str]
    errors: list[str]
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "checks": self.checks,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_formal_trade_plan(
    plan: TradePlan,
    *,
    runtime: RuntimeSettings,
    allowed_assets: set[str],
    wallet: dict[str, Any] | None,
    mark_price: float | None,
    max_leverage: float,
    minimum_order_usdc: float,
    require_leveraged_intraday: bool = True,
) -> FormalValidationResult:
    checks: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []
    asset = normalize_asset_symbol(plan.asset)
    effective_minimum = minimum_order_usdc + HYPERLIQUID_MIN_NOTIONAL_BUFFER_USDC

    if asset in allowed_assets:
        checks.append(f"{asset} is allowlisted.")
    else:
        errors.append(f"{asset} is not in the runtime allowlist.")

    if plan.network == runtime.network:
        checks.append(f"Plan network matches runtime ({runtime.network}).")
    else:
        errors.append(f"Plan network {plan.network} does not match runtime {runtime.network}.")

    if plan.status == "draft":
        checks.append("Plan is still a draft.")
    else:
        errors.append(f"Plan status must be draft before autonomous execution, got {plan.status}.")

    if plan.size_usdc >= effective_minimum:
        checks.append(
            f"Order value {plan.size_usdc:.2f} USDC clears buffered minimum "
            f"{effective_minimum:.2f} USDC."
        )
    else:
        errors.append(
            f"Order value must be at least {effective_minimum:.2f} USDC to clear "
            "Hyperliquid's 10 USDC minimum after size rounding."
        )

    if plan.size_usdc <= runtime.max_order_usdc:
        checks.append(f"Order value is within runtime max {runtime.max_order_usdc:.2f} USDC.")
    else:
        errors.append("Order value exceeds runtime max order.")

    if float(plan.leverage).is_integer():
        checks.append("Leverage is an integer.")
    else:
        errors.append("Leverage must be an integer.")

    if 1 <= plan.leverage <= max_leverage:
        checks.append(f"Leverage {plan.leverage:g}x is within max {max_leverage:g}x.")
    else:
        errors.append(f"Leverage must be between 1x and {max_leverage:g}x for {asset}.")

    if require_leveraged_intraday:
        if plan.leverage >= DEFAULT_INTRADAY_MIN_LEVERAGE:
            checks.append("Plan uses leveraged intraday exposure.")
        else:
            errors.append(
                f"Autonomous intraday trades require at least "
                f"{DEFAULT_INTRADAY_MIN_LEVERAGE:g}x leverage."
            )

    if plan.stop_loss is None or plan.take_profit is None:
        errors.append("Autonomous trades require both stop_loss and take_profit.")
    else:
        _validate_exit_direction(plan, mark_price, checks, errors)
        planned_loss = _planned_loss_usdc(plan)
        if planned_loss <= DEFAULT_MAX_PLANNED_LOSS_USDC:
            checks.append(f"Planned stop loss is capped at {planned_loss:.2f} USDC.")
        else:
            errors.append(
                f"Planned stop loss {planned_loss:.2f} USDC exceeds "
                f"{DEFAULT_MAX_PLANNED_LOSS_USDC:.2f} USDC autonomous cap."
            )

    if wallet is None:
        errors.append("Wallet state unavailable; margin sufficiency could not be verified.")
    else:
        withdrawable = _float(wallet.get("withdrawable_usdc"))
        margin_required = plan.size_usdc / max(plan.leverage, 1)
        if margin_required <= withdrawable:
            checks.append(
                f"Required margin {margin_required:.2f} USDC fits "
                f"withdrawable {withdrawable:.2f} USDC."
            )
        else:
            errors.append(
                f"Required margin {margin_required:.2f} USDC exceeds "
                f"withdrawable {withdrawable:.2f} USDC."
            )
        open_positions = wallet.get("open_positions") or []
        matching_positions = [
            item
            for item in open_positions
            if normalize_asset_symbol(item.get("position", {}).get("coin", "")) == asset
        ]
        if matching_positions:
            warnings.append(f"Wallet already has an open {asset} position.")
        else:
            checks.append(f"No existing {asset} position detected.")

    return FormalValidationResult(
        valid=not errors,
        checks=checks,
        errors=errors,
        warnings=warnings,
    )


def _validate_exit_direction(
    plan: TradePlan,
    mark_price: float | None,
    checks: list[str],
    errors: list[str],
) -> None:
    reference = mark_price or plan.entry_price
    if plan.side == TradeSide.long:
        if (
            plan.stop_loss < plan.entry_price < plan.take_profit
            and plan.stop_loss < reference < plan.take_profit
        ):
            checks.append("Long TP/SL bracket entry and current mark correctly.")
        else:
            errors.append(
                "Long plans require stop_loss below entry/mark and take_profit above entry/mark."
            )
    if plan.side == TradeSide.short:
        if (
            plan.take_profit < plan.entry_price < plan.stop_loss
            and plan.take_profit < reference < plan.stop_loss
        ):
            checks.append("Short TP/SL bracket entry and current mark correctly.")
        else:
            errors.append(
                "Short plans require take_profit below entry/mark and stop_loss above entry/mark."
            )


def _planned_loss_usdc(plan: TradePlan) -> float:
    if plan.stop_loss is None:
        return 0.0
    return abs(plan.entry_price - plan.stop_loss) / plan.entry_price * plan.size_usdc


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
