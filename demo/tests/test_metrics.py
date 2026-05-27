from hyper_demo.models import PositionSnapshot, TradeSide
from hyper_demo.services.metrics import compute_portfolio_metrics


def test_compute_portfolio_metrics_with_position() -> None:
    metrics = compute_portfolio_metrics(
        equity_curve=[1000, 1010, 1005, 1030, 1020],
        btc_benchmark=[100, 102, 101, 103, 104],
        eth_benchmark=[100, 101, 100, 102, 101],
        positions=[
            PositionSnapshot(
                asset="BTC",
                side=TradeSide.long,
                entry_price=100,
                mark_price=104,
                size_usdc=500,
                unrealized_pnl_usdc=20,
                leverage=1.5,
            )
        ],
    )

    assert metrics.equity_usdc == 1020
    assert metrics.exposure_by_asset["BTC"] == 750
    assert metrics.delta_like_exposure > 0
    assert metrics.value_at_risk_95 >= 0
