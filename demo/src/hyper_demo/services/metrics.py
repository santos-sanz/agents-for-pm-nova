from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats

from hyper_demo.models import PortfolioMetrics, PositionSnapshot, TradeSide


def _returns(values: list[float]) -> np.ndarray:
    if len(values) < 2:
        return np.array([], dtype=float)
    return pd.Series(values, dtype=float).pct_change().dropna().to_numpy()


def _max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    series = np.array(values, dtype=float)
    running_max = np.maximum.accumulate(series)
    drawdowns = (series - running_max) / np.where(running_max == 0, 1, running_max)
    return float(abs(drawdowns.min()))


def _beta(portfolio_returns: np.ndarray, benchmark_returns: np.ndarray) -> float:
    length = min(len(portfolio_returns), len(benchmark_returns))
    if length < 2:
        return 0.0
    p = portfolio_returns[-length:]
    b = benchmark_returns[-length:]
    if float(np.var(b)) == 0:
        return 0.0
    return float(stats.linregress(b, p).slope)


def _correlation(left: np.ndarray, right: np.ndarray) -> float:
    length = min(len(left), len(right))
    if length < 2:
        return 0.0
    corr = float(np.corrcoef(left[-length:], right[-length:])[0, 1])
    if math.isnan(corr):
        return 0.0
    return corr


def compute_portfolio_metrics(
    equity_curve: list[float],
    btc_benchmark: list[float],
    eth_benchmark: list[float],
    positions: list[PositionSnapshot],
    realized_pnl_usdc: float = 0.0,
) -> PortfolioMetrics:
    equity = equity_curve[-1] if equity_curve else 0.0
    portfolio_returns = _returns(equity_curve)
    btc_returns = _returns(btc_benchmark)
    eth_returns = _returns(eth_benchmark)

    beta = _beta(portfolio_returns, btc_returns)
    mean_return = float(portfolio_returns.mean()) if len(portfolio_returns) else 0.0
    btc_mean = float(btc_returns.mean()) if len(btc_returns) else 0.0
    alpha = mean_return - beta * btc_mean
    volatility = float(portfolio_returns.std() * math.sqrt(365)) if len(portfolio_returns) else 0.0
    sharpe_like = (
        float(mean_return / portfolio_returns.std() * math.sqrt(365))
        if len(portfolio_returns) and portfolio_returns.std() > 0
        else 0.0
    )
    var_95 = (
        abs(float(np.percentile(portfolio_returns, 5)) * equity)
        if len(portfolio_returns)
        else 0.0
    )

    exposure_by_asset: dict[str, float] = {}
    delta_like = 0.0
    unrealized = 0.0
    for position in positions:
        direction = 1 if position.side == TradeSide.long else -1
        exposure = direction * position.size_usdc * position.leverage
        exposure_by_asset[position.asset] = exposure_by_asset.get(position.asset, 0.0) + exposure
        delta_like += exposure / equity if equity else 0.0
        unrealized += position.unrealized_pnl_usdc

    return PortfolioMetrics(
        equity_usdc=round(float(equity), 2),
        alpha=round(float(alpha), 6),
        beta=round(float(beta), 4),
        delta_like_exposure=round(float(delta_like), 4),
        volatility=round(float(volatility), 4),
        max_drawdown=round(_max_drawdown(equity_curve), 4),
        sharpe_like=round(float(sharpe_like), 4),
        value_at_risk_95=round(float(var_95), 2),
        btc_correlation=round(_correlation(portfolio_returns, btc_returns), 4),
        eth_correlation=round(_correlation(portfolio_returns, eth_returns), 4),
        exposure_by_asset={asset: round(value, 2) for asset, value in exposure_by_asset.items()},
        realized_pnl_usdc=round(realized_pnl_usdc, 2),
        unrealized_pnl_usdc=round(unrealized, 2),
    )
