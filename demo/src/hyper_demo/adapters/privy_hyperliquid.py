from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from hyper_demo.adapters.hyperliquid import ExecutionBlocked, PreparedOrder, _extract_order_id
from hyper_demo.config import Settings, get_settings
from hyper_demo.models import (
    OrderRecord,
    PrivyAgentWallet,
    RuntimeNetwork,
    TradePlan,
    TradeSide,
    normalize_asset_symbol,
)

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "privy_hyperliquid.mjs"
DEMO_ROOT = SCRIPT_PATH.parent.parent


def _sanitized_exchange_reason(detail: str) -> str | None:
    for raw_line in detail.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        normalized = line.lower()
        if (
            normalized.startswith("at ")
            or "node_modules" in normalized
            or "file:///" in normalized
            or "/users/" in normalized
            or "traceback" in normalized
        ):
            continue
        if "apirequesterror" in normalized:
            line = line.split("ApiRequestError:", 1)[-1].strip()
        elif normalized.startswith("error "):
            line = line[6:].strip()
        if line and line.lower() not in {"error", "unknown error"}:
            return line[:240]
    return None


def _friendly_helper_error(detail: str) -> str:
    normalized = detail.lower()
    if "minimum value of $10" in normalized or "minimum value of 10" in normalized:
        return (
            "Order too small. Hyperliquid requires a minimum order value of 10 USDC. "
            "Increase Size to at least 10 USDC and try again."
        )
    if "insufficient" in normalized and ("margin" in normalized or "balance" in normalized):
        return (
            "Not enough available margin for this order. Reduce Size or Leverage, "
            "or add more collateral before trying again."
        )
    if "reduce only" in normalized and "position" in normalized:
        return "Reduce-only order blocked because there is no matching open position to reduce."
    if "price" in normalized and ("invalid" in normalized or "tick" in normalized):
        return (
            "Invalid price for this market. Adjust the limit price closer to "
            "the current mark price."
        )
    if "invalid safe integer" in normalized:
        return (
            "Invalid leverage. Hyperliquid only accepts whole-number leverage. "
            "Use 1x, 2x, 3x, and so on."
        )
    reason = _sanitized_exchange_reason(detail)
    if reason:
        return (
            "Hyperliquid rejected this order before execution. "
            f"Exchange reason: {reason}. "
            "Check Size, Leverage, available margin, and TP/SL prices, then try again."
        )
    return (
        "Hyperliquid rejected this order before execution. Check Size, Leverage, "
        "available margin, and TP/SL prices, then try again."
    )


class PrivyHyperliquidAdapter:
    """Hyperliquid execution through Privy server wallets and agent wallets."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def setup_agent_wallet(
        self,
        network: RuntimeNetwork,
        current: PrivyAgentWallet | None = None,
        master_wallet_id: str | None = None,
        master_wallet_address: str | None = None,
    ) -> PrivyAgentWallet:
        self._validate_privy_config()
        payload: dict[str, Any] = {
            "network": network.value,
            "agentName": "HyperClaude",
        }
        if master_wallet_id and master_wallet_address:
            payload.update(
                {
                    "masterWalletId": master_wallet_id,
                    "masterWalletAddress": master_wallet_address,
                }
            )
        if current:
            payload.update(
                {
                    "masterWalletId": current.master_wallet_id,
                    "masterWalletAddress": current.master_wallet_address,
                    "agentWalletId": current.agent_wallet_id,
                    "agentWalletAddress": current.agent_wallet_address,
                    "agentName": "HyperClaude",
                }
            )
        result = self._run_helper("setup-agent", payload)
        return PrivyAgentWallet(
            network=network,
            master_wallet_id=result["masterWallet"]["id"],
            master_wallet_address=result["masterWallet"]["address"],
            agent_wallet_id=result["agentWallet"]["id"],
            agent_wallet_address=result["agentWallet"]["address"],
            agent_name=result.get("agentName") or "HyperClaude",
            registered=bool(result.get("registered")),
            raw_response=result,
        )

    def execute_plan(
        self,
        plan: TradePlan,
        runtime_agent: PrivyAgentWallet,
        confirmed: bool,
        confirmation_phrase: str | None = None,
    ) -> OrderRecord:
        self._validate_execution(plan, runtime_agent, confirmed, confirmation_phrase)
        prepared = self.prepare_order(plan)
        result = self._run_helper(
            "execute-plan",
            {
                "network": plan.network.value,
                "agentWalletId": runtime_agent.agent_wallet_id,
                "agentWalletAddress": runtime_agent.agent_wallet_address,
                "masterWalletAddress": runtime_agent.master_wallet_address,
                "plan": {
                    "id": plan.id,
                    "asset": plan.asset,
                    "side": plan.side.value,
                    "entryType": plan.entry_type,
                    "entryPrice": prepared.entry_price,
                    "size": prepared.size,
                    "leverage": plan.leverage,
                    "stopLoss": prepared.stop_loss,
                    "takeProfit": prepared.take_profit,
                },
            },
        )
        exchange_name = (
            "hyperliquid-mainnet"
            if plan.network == RuntimeNetwork.prodnet
            else "hyperliquid-testnet"
        )
        return OrderRecord(
            plan_id=plan.id,
            exchange=exchange_name,
            asset=plan.asset,
            side=plan.side,
            size_usdc=plan.size_usdc,
            entry_order_id=_extract_order_id(result.get("entry")),
            stop_order_id=_extract_order_id(result.get("stopLoss")),
            take_profit_order_id=_extract_order_id(result.get("takeProfit")),
            raw_response=result,
            status="submitted",
            message="Submitted order through Privy Hyperliquid agent wallet.",
        )

    def wallet_state(self, agent: PrivyAgentWallet) -> dict[str, Any]:
        self._validate_privy_config()
        return self._run_helper(
            "wallet-state",
            {
                "network": agent.network.value,
                "masterWalletAddress": agent.master_wallet_address,
                "agentWalletAddress": agent.agent_wallet_address,
            },
        )

    def close_position(
        self,
        agent: PrivyAgentWallet,
        asset: str,
        size: float,
        side: TradeSide,
        position_value_usdc: float,
        confirmed: bool,
    ) -> OrderRecord:
        self._validate_privy_config()
        if not confirmed:
            raise ExecutionBlocked("Confirm position close before submitting a reduce-only order.")
        result = self._run_helper(
            "close-position",
            {
                "network": agent.network.value,
                "agentWalletId": agent.agent_wallet_id,
                "agentWalletAddress": agent.agent_wallet_address,
                "asset": asset,
                "size": size,
                "side": side.value,
            },
        )
        exchange_name = (
            "hyperliquid-mainnet"
            if agent.network == RuntimeNetwork.prodnet
            else "hyperliquid-testnet"
        )
        return OrderRecord(
            plan_id="manual_position_close",
            exchange=exchange_name,
            asset=asset,
            side=TradeSide.short if side == TradeSide.long else TradeSide.long,
            size_usdc=position_value_usdc,
            entry_order_id=_extract_order_id(result.get("close")),
            raw_response=result,
            status="submitted",
            message=f"Submitted reduce-only close order for {asset}.",
        )

    def set_position_protection(
        self,
        agent: PrivyAgentWallet,
        asset: str,
        size: float,
        side: TradeSide,
        take_profit: float | None,
        stop_loss: float | None,
        confirmed: bool,
    ) -> dict[str, Any]:
        self._validate_privy_config()
        if not confirmed:
            raise ExecutionBlocked("Confirm TP/SL before submitting reduce-only trigger orders.")
        if take_profit is None and stop_loss is None:
            raise ExecutionBlocked("Set at least one take profit or stop loss price.")
        return self._run_helper(
            "set-protection",
            {
                "network": agent.network.value,
                "agentWalletId": agent.agent_wallet_id,
                "agentWalletAddress": agent.agent_wallet_address,
                "asset": asset,
                "size": size,
                "side": side.value,
                "takeProfit": take_profit,
                "stopLoss": stop_loss,
            },
        )

    def deposit_master_collateral(
        self,
        agent: PrivyAgentWallet,
        amount_usdc: float,
        confirmed: bool,
        confirmation_phrase: str | None,
    ) -> dict[str, Any]:
        self._validate_privy_config()
        if not confirmed:
            raise ExecutionBlocked("Confirm the master wallet deposit before submitting.")
        if agent.network != RuntimeNetwork.prodnet:
            raise ExecutionBlocked("Integrated master deposits are only configured for prodnet.")
        if not self.settings.hyperliquid_mainnet_enabled:
            raise ExecutionBlocked(
                "Mainnet is disabled. Set HYPERLIQUID_MAINNET_ENABLED=true to proceed."
            )
        if amount_usdc < 5:
            raise ExecutionBlocked("Hyperliquid Bridge2 deposits require at least 5 USDC.")
        return self._run_helper(
            "deposit-master",
            {
                "network": agent.network.value,
                "masterWalletId": agent.master_wallet_id,
                "masterWalletAddress": agent.master_wallet_address,
                "amountUsdc": amount_usdc,
            },
        )

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

    def _validate_execution(
        self,
        plan: TradePlan,
        agent: PrivyAgentWallet,
        confirmed: bool,
        confirmation_phrase: str | None,
    ) -> None:
        self._validate_privy_config()
        if self.settings.demo_require_confirmation and not confirmed:
            raise ExecutionBlocked(
                "Explicit confirmation is required before submitting Hyperliquid orders."
            )
        if not agent.registered:
            raise ExecutionBlocked("Privy Hyperliquid agent wallet is not registered.")
        if agent.network != plan.network:
            raise ExecutionBlocked("Privy agent wallet network does not match the trade plan.")
        asset = normalize_asset_symbol(plan.asset)
        if asset not in self.settings.allowed_assets_set:
            raise ExecutionBlocked(f"{asset} is not in the runtime allowed assets.")
        if plan.size_usdc > self.settings.hyperliquid_max_order_usdc:
            raise ExecutionBlocked(
                "Order size exceeds HYPERLIQUID_MAX_ORDER_USDC "
                f"({self.settings.hyperliquid_max_order_usdc} USDC)."
            )
        if plan.network == RuntimeNetwork.prodnet:
            if not self.settings.hyperliquid_mainnet_enabled:
                raise ExecutionBlocked(
                    "Mainnet is disabled. Set HYPERLIQUID_MAINNET_ENABLED=true to proceed."
                )

    def _validate_privy_config(self) -> None:
        if not self.settings.privy_execution_enabled:
            raise ExecutionBlocked("Set PRIVY_EXECUTION_ENABLED=true to use Privy execution.")
        if not self.settings.has_privy_server_credentials:
            raise ExecutionBlocked("Set PRIVY_APP_ID and PRIVY_APP_SECRET for Privy execution.")
        if not SCRIPT_PATH.exists():
            raise ExecutionBlocked(f"Privy Hyperliquid helper is missing: {SCRIPT_PATH}")

    def _run_helper(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        secret = self.settings.privy_app_secret
        env = {
            **os.environ,
            "NODE_PATH": str(DEMO_ROOT / "node_modules"),
            "PRIVY_APP_ID": self.settings.privy_app_id or "",
            "PRIVY_APP_SECRET": secret.get_secret_value() if secret else "",
        }
        try:
            completed = subprocess.run(
                ["node", str(SCRIPT_PATH), command],
                input=json.dumps(payload),
                capture_output=True,
                check=False,
                encoding="utf-8",
                env=env,
                cwd=DEMO_ROOT,
                timeout=150,
            )
        except FileNotFoundError as exc:
            raise ExecutionBlocked("Node.js is required for Privy Hyperliquid execution.") from exc
        except subprocess.TimeoutExpired as exc:
            raise ExecutionBlocked("Privy Hyperliquid helper timed out.") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
            raise ExecutionBlocked(_friendly_helper_error(detail))
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ExecutionBlocked("Privy Hyperliquid helper returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise ExecutionBlocked("Privy Hyperliquid helper returned an invalid payload.")
        return payload
