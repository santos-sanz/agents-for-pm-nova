from __future__ import annotations

from statistics import fmean, pstdev

from hyper_demo.models import (
    AgentTradeAnalysis,
    Candle,
    InvestorProfile,
    ResearchReport,
    RuntimeSettings,
    TimeframeSignal,
    TradeCandidate,
    TradePlan,
    TradeSide,
)
from hyper_demo.services.market import MarketDataClient
from hyper_demo.services.proposals import infer_side

TIMEFRAME_LIMITS = {
    "15m": 96,
    "1h": 96,
    "4h": 72,
    "1d": 60,
}

RISK_SETTINGS = {
    "conservative": {"stop_scale": 0.75, "max_rr": 1.8, "min_score": 48.0},
    "balanced": {"stop_scale": 0.95, "max_rr": 2.25, "min_score": 42.0},
    "aggressive": {"stop_scale": 1.15, "max_rr": 2.85, "min_score": 36.0},
}

CLOSE_WINDOW_SETTINGS = {
    "15m": {
        "preferred": {"15m"},
        "usable": {"15m", "1h"},
        "max_stop_pct": 1.25,
        "max_take_pct": 2.25,
    },
    "1h": {
        "preferred": {"15m", "1h"},
        "usable": {"15m", "1h", "4h"},
        "max_stop_pct": 2.0,
        "max_take_pct": 4.0,
    },
    "4h": {
        "preferred": {"1h", "4h"},
        "usable": {"1h", "4h", "1d"},
        "max_stop_pct": 3.25,
        "max_take_pct": 7.0,
    },
    "1d": {
        "preferred": {"4h", "1d"},
        "usable": {"1h", "4h", "1d"},
        "max_stop_pct": 5.0,
        "max_take_pct": 11.0,
    },
}


def build_agent_trade_analysis(
    asset: str,
    runtime: RuntimeSettings,
    profile: InvestorProfile,
    report: ResearchReport,
    market: MarketDataClient,
    *,
    risk_appetite: str = "balanced",
    close_window: str = "1h",
) -> AgentTradeAnalysis:
    candles_by_timeframe = {
        interval: market.candles(asset, interval, limit)
        for interval, limit in TIMEFRAME_LIMITS.items()
    }
    signals = [
        analyze_timeframe(interval, candles)
        for interval, candles in candles_by_timeframe.items()
    ]
    max_leverage = _market_max_leverage(asset, market)
    candidates = build_trade_candidates(
        profile=profile,
        runtime=runtime,
        report=report,
        signals=signals,
        candles_by_timeframe=candles_by_timeframe,
        max_leverage=max_leverage,
        risk_appetite=risk_appetite,
        close_window=close_window,
    )
    best = candidates[0]
    directional_score = _directional_consensus(signals)
    direction_label = "long" if directional_score >= 0 else "short"
    return AgentTradeAnalysis(
        asset=asset,
        network=runtime.network,
        thesis=report.thesis,
        summary=(
            f"Claude research and local market structure favor a {direction_label} setup. "
            f"The selected {best.entry_type} order uses {best.timeframe} as the execution anchor "
            f"with {best.leverage:.2f}x leverage inside configured limits."
        ),
        best_candidate=best,
        candidates=candidates,
        timeframes=signals,
        candles_by_timeframe=candles_by_timeframe,
        sources=report.sources,
        fallback_used=report.fallback_used or any(
            candle.source == "fallback"
            for candles in candles_by_timeframe.values()
            for candle in candles
        ),
    )


def analyze_timeframe(interval: str, candles: list[Candle]) -> TimeframeSignal:
    if len(candles) < 5:
        raise ValueError(f"At least 5 candles are required for {interval} analysis.")
    closes = [candle.close for candle in candles]
    highs = [candle.high for candle in candles]
    lows = [candle.low for candle in candles]
    returns = [
        (closes[index] - closes[index - 1]) / closes[index - 1]
        for index in range(1, len(closes))
        if closes[index - 1] > 0
    ]
    return_pct = (closes[-1] - closes[0]) / closes[0] * 100
    volatility_pct = (pstdev(returns) * 100) if len(returns) > 1 else 0.0
    rsi = _rsi(closes)
    atr_pct = _atr_pct(candles)
    fast = fmean(closes[-min(8, len(closes)):])
    slow = fmean(closes[-min(24, len(closes)):])
    trend_component = 18 if fast > slow else -18 if fast < slow else 0
    rsi_component = max(-24.0, min(24.0, (rsi - 50) * 0.8))
    return_component = max(-44.0, min(44.0, return_pct * 5.0))
    volatility_penalty = min(14.0, volatility_pct * 2.2)
    raw_score = return_component + trend_component + rsi_component
    if raw_score > 0:
        raw_score -= volatility_penalty
    elif raw_score < 0:
        raw_score += volatility_penalty
    score = round(max(-100.0, min(100.0, raw_score)), 2)
    direction = "bullish" if score >= 12 else "bearish" if score <= -12 else "neutral"
    support = min(lows[-min(24, len(lows)):])
    resistance = max(highs[-min(24, len(highs)):])
    reason = (
        f"{direction.title()} structure: {return_pct:+.2f}% return, RSI {rsi:.1f}, "
        f"ATR {atr_pct:.2f}%."
    )
    return TimeframeSignal(
        interval=interval,  # type: ignore[arg-type]
        direction=direction,  # type: ignore[arg-type]
        score=score,
        return_pct=round(return_pct, 4),
        volatility_pct=round(max(0.0, volatility_pct), 4),
        rsi=round(rsi, 2),
        atr_pct=round(atr_pct, 4),
        support=round(support, 6),
        resistance=round(resistance, 6),
        reason=reason,
    )


def build_trade_candidates(
    profile: InvestorProfile,
    runtime: RuntimeSettings,
    report: ResearchReport,
    signals: list[TimeframeSignal],
    candles_by_timeframe: dict[str, list[Candle]],
    max_leverage: int,
    risk_appetite: str = "balanced",
    close_window: str = "1h",
) -> list[TradeCandidate]:
    qualitative_side = infer_side(report)
    risk_settings = RISK_SETTINGS.get(risk_appetite, RISK_SETTINGS["balanced"])
    window_settings = CLOSE_WINDOW_SETTINGS.get(close_window, CLOSE_WINDOW_SETTINGS["1h"])
    candidates: list[TradeCandidate] = []
    for signal in signals:
        if signal.interval not in window_settings["usable"]:
            continue
        candles = candles_by_timeframe[signal.interval]
        current = candles[-1].close
        for side in (TradeSide.long, TradeSide.short):
            side_score = signal.score if side == TradeSide.long else -signal.score
            qualitative = 8 if side == qualitative_side else -6
            timeframe_bonus = _timeframe_fit_bonus(signal.interval, window_settings)
            base_score = max(
                0.0,
                min(100.0, 50 + side_score * 0.38 + qualitative + timeframe_bonus),
            )
            if base_score < float(risk_settings["min_score"]):
                continue
            for entry_type in ("market", "limit"):
                score = base_score + (3 if entry_type == "limit" and signal.atr_pct >= 0.35 else 0)
                entry_price = _entry_price(current, signal, side, entry_type)
                stop_pct = _bounded_stop_pct(signal, risk_settings, window_settings)
                risk_reward = round(
                    max(1.15, min(float(risk_settings["max_rr"]), 1.2 + score / 95)),
                    2,
                )
                stop_loss, take_profit, realized_stop_pct = _exits(
                    entry_price,
                    current,
                    side,
                    stop_pct,
                    risk_reward,
                    float(window_settings["max_take_pct"]),
                )
                if not _candidate_levels_are_actionable(
                    side,
                    current,
                    entry_price,
                    stop_loss,
                    take_profit,
                ):
                    continue
                size_usdc = round(
                    min(runtime.max_order_usdc, profile.max_position_notional_usdc),
                    2,
                )
                max_loss_usdc = round(size_usdc * realized_stop_pct / 100, 2)
                leverage = _recommended_leverage(
                    score,
                    profile.recommended_leverage_cap,
                    max_leverage,
                )
                candidates.append(
                    TradeCandidate(
                        side=side,
                        entry_type=entry_type,  # type: ignore[arg-type]
                        timeframe=signal.interval,
                        score=round(max(0.0, min(100.0, score)), 2),
                        confidence=round(max(0.1, min(0.92, score / 100)), 2),
                        entry_price=round(entry_price, 6),
                        stop_loss=round(stop_loss, 6),
                        take_profit=round(take_profit, 6),
                        size_usdc=size_usdc,
                        max_loss_usdc=max(0.01, max_loss_usdc),
                        leverage=leverage,
                        risk_reward=risk_reward,
                        rationale=(
                            f"{signal.interval} {signal.direction} signal with {entry_type} entry. "
                            "Score reflects local trend/RSI/ATR and Claude's "
                            f"{qualitative_side.value} bias."
                        ),
                    )
                )
    return _balanced_candidates(candidates)


def _balanced_candidates(candidates: list[TradeCandidate]) -> list[TradeCandidate]:
    ranked = sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
    selected: list[TradeCandidate] = []
    seen: set[tuple[str, str, str, float]] = set()

    def add(candidate: TradeCandidate) -> None:
        key = (
            candidate.side.value,
            candidate.entry_type,
            candidate.timeframe,
            candidate.entry_price,
        )
        if key in seen:
            return
        selected.append(candidate)
        seen.add(key)

    if ranked:
        add(ranked[0])
    for entry_type in ("market", "limit"):
        candidate = next((item for item in ranked if item.entry_type == entry_type), None)
        if candidate:
            add(candidate)
    for timeframe in ("15m", "1h", "4h", "1d"):
        candidate = next((item for item in ranked if item.timeframe == timeframe), None)
        if candidate:
            add(candidate)
    for candidate in ranked:
        if len(selected) >= 8:
            break
        add(candidate)
    return selected[:8]


def _timeframe_fit_bonus(interval: str, window_settings: dict[str, object]) -> float:
    preferred = window_settings["preferred"]
    usable = window_settings["usable"]
    if isinstance(preferred, set) and interval in preferred:
        return 9.0
    if isinstance(usable, set) and interval in usable:
        return 1.0
    return -18.0


def trade_plan_from_candidate(
    asset: str,
    profile: InvestorProfile,
    report: ResearchReport,
    runtime: RuntimeSettings,
    candidate: TradeCandidate,
) -> TradePlan:
    stop_loss = candidate.stop_loss if candidate.leverage >= 10 else None
    max_loss_usdc = candidate.max_loss_usdc if stop_loss is not None else 0.0
    rationale = candidate.rationale
    if stop_loss is None:
        rationale = (
            f"{rationale} No stop-loss is attached because leverage is below 10x; "
            "use active monitoring, thesis invalidation, and take-profit for the intraday exit."
        )
    return TradePlan(
        asset=asset,
        side=candidate.side,
        size_usdc=candidate.size_usdc,
        entry_type=candidate.entry_type,
        entry_price=candidate.entry_price,
        stop_loss=stop_loss,
        take_profit=candidate.take_profit,
        max_loss_usdc=max_loss_usdc,
        leverage=candidate.leverage,
        profile_id=profile.id,
        research_id=report.id,
        rationale=rationale,
        invalidation_criteria=report.why_not_invest[:3]
        or [
            "The selected timeframe flips direction against the trade.",
            "Take-profit or thesis invalidation cannot be verified before execution.",
        ],
        confidence=candidate.confidence,
        thesis=report.thesis,
        evidence=report.evidence,
        network=runtime.network,
        agent_session_id=report.agent_session_id,
        raw_agent_output=report.raw_agent_output,
        execution_message="Proposed for manual review. Execute is required to submit orders.",
    )


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) <= period:
        return 50.0
    gains: list[float] = []
    losses: list[float] = []
    for index in range(len(closes) - period, len(closes)):
        change = closes[index] - closes[index - 1]
        if change >= 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(change))
    avg_gain = fmean(gains) if gains else 0.0
    avg_loss = fmean(losses) if losses else 0.0
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    relative_strength = avg_gain / avg_loss
    return 100 - (100 / (1 + relative_strength))


def _atr_pct(candles: list[Candle], period: int = 14) -> float:
    window = candles[-min(period + 1, len(candles)):]
    ranges: list[float] = []
    for index, candle in enumerate(window):
        previous_close = window[index - 1].close if index else candle.close
        ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )
    close = candles[-1].close
    if close <= 0:
        return 0.0
    return fmean(ranges) / close * 100


def _entry_price(
    current: float,
    signal: TimeframeSignal,
    side: TradeSide,
    entry_type: str,
) -> float:
    if entry_type == "market":
        return current
    offset_pct = max(0.08, min(0.65, signal.atr_pct * 0.28)) / 100
    if side == TradeSide.long:
        return current * (1 - offset_pct)
    return current * (1 + offset_pct)


def _bounded_stop_pct(
    signal: TimeframeSignal,
    risk_settings: dict[str, float],
    window_settings: dict[str, object],
) -> float:
    raw = (signal.atr_pct or 1.0) * 1.15 * float(risk_settings["stop_scale"])
    return max(0.45, min(float(window_settings["max_stop_pct"]), raw))


def _exits(
    entry_price: float,
    current_price: float,
    side: TradeSide,
    stop_pct: float,
    risk_reward: float,
    max_take_pct: float,
) -> tuple[float, float, float]:
    max_take_pct = max(stop_pct * 1.1, max_take_pct)
    return _exits_with_take_cap(
        entry_price,
        current_price,
        side,
        stop_pct,
        risk_reward,
        max_take_pct,
    )


def _exits_with_take_cap(
    entry_price: float,
    current_price: float,
    side: TradeSide,
    stop_pct: float,
    risk_reward: float,
    max_take_pct: float,
) -> tuple[float, float, float]:
    take_pct = min(stop_pct * risk_reward, max_take_pct)
    if take_pct < stop_pct * 1.1:
        stop_pct = max(0.35, take_pct / 1.1)
    stop_distance = entry_price * stop_pct / 100
    take_distance = entry_price * take_pct / 100
    if side == TradeSide.long:
        stop_loss = entry_price - stop_distance
        take_profit = entry_price + take_distance
        minimum_take = max(entry_price, current_price) * 1.002
        if take_profit < minimum_take:
            take_profit = minimum_take
    else:
        stop_loss = entry_price + stop_distance
        take_profit = entry_price - take_distance
        maximum_take = min(entry_price, current_price) * 0.998
        if take_profit > maximum_take:
            take_profit = maximum_take
    return stop_loss, take_profit, stop_pct


def _candidate_levels_are_actionable(
    side: TradeSide,
    current_price: float,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
) -> bool:
    if side == TradeSide.long:
        return stop_loss < min(entry_price, current_price) and take_profit > max(
            entry_price,
            current_price,
        )
    return take_profit < min(entry_price, current_price) and stop_loss > max(
        entry_price,
        current_price,
    )


def _recommended_leverage(score: float, profile_cap: float, max_leverage: int) -> float:
    exchange_cap = max_leverage if max_leverage > 0 else 10
    confidence_cap = 1.0 + (score / 100) * 2.0
    leverage = min(10.0, float(exchange_cap), profile_cap, confidence_cap)
    return float(max(1, round(leverage)))


def _market_max_leverage(asset: str, market: MarketDataClient) -> int:
    try:
        assets = market.available_assets()
    except Exception:
        return 0
    for market_asset in assets:
        if market_asset.symbol == asset:
            return market_asset.max_leverage
    return 0


def _directional_consensus(signals: list[TimeframeSignal]) -> float:
    if not signals:
        return 0
    weights = {"15m": 0.16, "1h": 0.24, "4h": 0.36, "1d": 0.24}
    return sum(signal.score * weights.get(signal.interval, 0.25) for signal in signals)
