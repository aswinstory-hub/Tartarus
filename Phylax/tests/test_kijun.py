from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from Engines.kijun import Kijun


def _trade(net: float, gross: float, costs: float, day: int) -> dict[str, object]:
    entry = datetime(2025, 1, day, tzinfo=UTC)
    return {
        "entry_time": entry,
        "exit_time": entry + timedelta(hours=2),
        "entry_price": 100.0,
        "exit_price": 100.0 + gross,
        "quantity": 2,
        "gross_pnl": gross,
        "costs": costs,
        "net_pnl": net,
    }


def test_analyze_reports_realized_metrics_and_optional_returns() -> None:
    report = Kijun().analyze([_trade(18, 20, 2, 1), _trade(-12, -10, 2, 2)], initial_capital=1000)

    assert report.metrics["trade_count"] == 2
    assert report.metrics["total_net_pnl"] == 6
    assert report.metrics["win_rate"] == 0.5
    assert report.metrics["average_win"] == 18
    assert report.metrics["average_loss"] == -12
    assert report.metrics["maximum_drawdown_amount"] == 12
    assert report.metrics["total_return_pct"] == 0.6
    assert report.metrics["maximum_drawdown_pct"] == pytest.approx(12 / 1018 * 100)
    assert report.metrics["annualized_return_pct"] is not None
    assert report.metrics["profit_factor"] == pytest.approx(1.5)
    assert report.metrics["best_trade"] == 18
    assert report.metrics["worst_trade"] == -12
    assert len(report.curves["equity_curve"]) == 3
    assert report.curves["equity_curve"][-1]["value"] == 1006
    assert report.curves["drawdown_curve"][-1]["amount"] == 12


def test_empty_run_keeps_undefined_metrics_none() -> None:
    report = Kijun().analyze([])

    assert report.metrics["trade_count"] == 0
    assert report.metrics["total_net_pnl"] == 0
    assert report.metrics["win_rate"] is None
    assert report.metrics["average_win"] is None
    assert report.metrics["maximum_drawdown_pct"] is None
    assert report.metrics["total_return_pct"] is None
    assert report.metrics["sharpe_ratio"] is None
    assert report.metrics["sortino_ratio"] is None


def test_empty_run_with_capital_and_date_range_reports_zero_returns() -> None:
    report = Kijun().analyze(
        [],
        initial_capital=1000,
        metadata={
            "data_range": {
                "start_inclusive": "2025-01-01",
                "end_exclusive": "2025-07-01",
            }
        },
    )

    assert report.metrics["ending_capital"] == 1000
    assert report.metrics["total_return_pct"] == 0
    assert report.metrics["annualized_return_pct"] == 0


def test_annualized_return_uses_backtest_window_from_metadata() -> None:
    report = Kijun().analyze(
        [_trade(100, 100, 0, 1)],
        initial_capital=1000,
        metadata={
            "data_range": {
                "start_inclusive": "2024-01-01",
                "end_exclusive": "2025-01-01",
            }
        },
    )

    assert report.metrics["annualized_return_pct"] == pytest.approx(9.9785182458)
    assert report.metrics["cagr_pct"] == report.metrics["annualized_return_pct"]
    assert report.metrics["net_return_pct"] == report.metrics["total_return_pct"]


def test_periodic_equity_calculates_annualized_sharpe_and_sortino() -> None:
    equity = pd.Series(
        [100.0, 110.0, 99.0, 108.9],
        index=pd.date_range("2025-01-01", periods=4, freq="D", tz="UTC"),
    )

    report = Kijun().analyze([], periodic_equity=equity, periods_per_year=252)

    assert report.metrics["sharpe_ratio"] is not None
    assert report.metrics["sortino_ratio"] is not None
    assert report.metrics["periods_per_year"] == 252
    assert len(report.curves["periodic_equity_curve"]) == 4


def test_cost_components_and_underwater_time_use_explicit_assumptions() -> None:
    trades = [
        _trade(18, 20, 2, 1),
        _trade(-12, -10, 2, 2),
        _trade(12, 12, 0, 5),
    ]
    # Each cost field matches both Buroka sides and the configured multiplier.
    trades[0]["costs"] = 1.76
    trades[0]["net_pnl"] = 18.24
    trades[1]["costs"] = 1.52
    trades[1]["net_pnl"] = -11.52
    trades[2]["costs"] = 1.696
    trades[2]["net_pnl"] = 10.304
    metadata = {
        "costs_and_fill_assumptions": {
            "fee_rate": 0.001,
            "spread_bps": 10,
            "slippage_bps": 5,
        },
        "broker_settings": {"pnl_multiplier": 2},
        "data_range": {
            "start_inclusive": "2025-01-01",
            "end_exclusive": "2025-01-06T02:00:00Z",
        },
    }

    report = Kijun().analyze(trades, initial_capital=1000, metadata=metadata)

    assert report.metrics["total_costs"] == pytest.approx(4.976)
    assert report.metrics["total_fee_cost"] == pytest.approx(2.488)
    assert report.metrics["total_spread_cost"] == pytest.approx(1.244)
    assert report.metrics["total_slippage_cost"] == pytest.approx(1.244)
    assert report.metrics["slippage_bps"] == 5
    assert report.metrics["maximum_time_underwater_days"] == pytest.approx(4)
    assert report.metrics["time_underwater_days"] == pytest.approx(4)


def test_save_writes_machine_and_human_readable_reports(tmp_path) -> None:
    engine = Kijun()
    report = engine.analyze([], metadata={"strategy": "test"})

    paths = engine.save(report, output_dir=tmp_path, stem="sample")

    assert [path.name for path in paths] == ["sample.json", "sample.csv", "sample.txt"]
    assert all(path.is_file() for path in paths)
    assert "Backtest report" in paths[2].read_text(encoding="utf-8")
    assert "equity_curve" in paths[0].read_text(encoding="utf-8")
    assert "time,equity" in (tmp_path / "sample-equity.csv").read_text(encoding="utf-8")
    assert (tmp_path / "sample-drawdown.csv").is_file()


def test_dashboard_has_overview_and_individual_panes() -> None:
    engine = Kijun()
    report = engine.analyze([_trade(18, 20, 2, 1)], initial_capital=1000)

    overview = engine.render_dashboard(report, width=100)
    trades = engine.render_dashboard(report, view="trades", width=100)
    equity = engine.render_dashboard(report, view="equity", width=100)
    drawdown = engine.render_dashboard(report, view="drawdown", width=100)

    assert "KIJUN" in overview
    assert "Equity Curve" in overview
    assert "Drawdown Curve" in overview
    assert "2025-01-01" in overview
    assert "Equity Curve" in equity
    assert "2025-01-01" in equity
    assert "Drawdown Curve" in drawdown
    assert "2025-01-01" in drawdown
    assert "Closed Trades" in trades
    assert "18" in trades

    metrics = engine.render_dashboard(report, view="metrics", width=120)
    for label in (
        "Net Return Pct",
        "Maximum Drawdown Amount",
        "Profit Factor",
        "Win Rate",
        "Average Win",
        "Average Loss",
        "Expectancy Per Trade",
        "Trade Count",
        "Total Costs",
        "Total Slippage Cost",
        "Cagr Pct",
        "Sharpe Ratio",
        "Sortino Ratio",
        "Calmar Ratio",
        "Time In Market Pct",
        "Price Notional Turnover",
        "Recovery Factor",
        "Time Underwater Days",
    ):
        assert label in metrics


def test_exposure_merges_overlapping_trades_and_streaks_follow_exit_time() -> None:
    first = _trade(5, 5, 0, 1)
    second = _trade(-2, -2, 0, 1)
    first["entry_time"] = datetime(2025, 1, 1, tzinfo=UTC)
    first["exit_time"] = datetime(2025, 1, 1, 4, tzinfo=UTC)
    second["entry_time"] = datetime(2025, 1, 1, 2, tzinfo=UTC)
    second["exit_time"] = datetime(2025, 1, 1, 6, tzinfo=UTC)

    report = Kijun().analyze(
        [first, second],
        metadata={
            "data_range": {
                "start_inclusive": "2025-01-01T00:00:00Z",
                "end_exclusive": "2025-01-02T00:00:00Z",
            }
        },
    )

    assert report.metrics["time_in_market_pct"] == pytest.approx(25.0)
    assert report.metrics["maximum_consecutive_wins"] == 1
    assert report.metrics["maximum_consecutive_losses"] == 1
