from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from Engines import kijun as kijun_module
from Engines.kijun import Kijun
from Engines.kijun_dashboard import (
    load_history_records,
    load_report,
    load_selected_run,
)


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
    assert report.metrics["maximum_drawdown_pct"] == 1.179
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

    assert report.metrics["annualized_return_pct"] == 9.979
    assert report.metrics["cagr_pct"] == report.metrics["annualized_return_pct"]
    assert report.metrics["net_return_pct"] == report.metrics["total_return_pct"]


def test_metric_values_round_to_three_decimals_and_counts_stay_integers() -> None:
    report = Kijun().analyze([_trade(1.23456, 1.34567, 0.11111, 1)])

    assert report.metrics["total_net_pnl"] == 1.235
    assert report.metrics["trade_count"] == 1
    assert isinstance(report.metrics["trade_count"], int)


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


def test_marked_equity_drives_account_return_and_drawdown() -> None:
    equity = pd.Series(
        [1000.0, 1100.0, 900.0, 1050.0],
        index=pd.date_range("2025-01-01", periods=4, freq="D", tz="UTC"),
    )

    report = Kijun().analyze([], initial_capital=1000, periodic_equity=equity)

    assert report.metrics["total_net_pnl"] == 0
    assert report.metrics["marked_net_pnl"] == 50
    assert report.metrics["net_pnl"] == 50
    assert report.metrics["ending_capital"] == 1050
    assert report.metrics["total_return_pct"] == 5
    assert report.metrics["maximum_drawdown_amount"] == 200
    assert report.metrics["maximum_drawdown_pct"] == 18.182
    assert report.curves["equity_curve"] == report.curves["periodic_equity_curve"]
    assert report.curves["drawdown_curve"][2]["amount"] == 200


def test_nonpositive_marked_equity_keeps_curve_but_leaves_risk_ratios_undefined() -> None:
    equity = pd.Series(
        [1000.0, 0.0, -10.0],
        index=pd.date_range("2025-01-01", periods=3, freq="D", tz="UTC"),
    )

    report = Kijun().analyze([], initial_capital=1000, periodic_equity=equity)

    assert report.metrics["sharpe_ratio"] is None
    assert report.metrics["sortino_ratio"] is None
    assert report.metrics["ending_capital"] == -10
    assert report.curves["equity_curve"][-1]["value"] == -10


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


def test_save_keeps_latest_and_appends_compact_history(tmp_path) -> None:
    engine = Kijun()
    report = engine.analyze([_trade(18, 20, 2, 1)], metadata={"strategy": "Test Strategy"})

    latest_path = engine.save(report, output_root=tmp_path)
    latest = load_report(latest_path)
    history_path = tmp_path / "test_strategy" / "history.jsonl"
    records = load_history_records(history_path)

    assert latest_path == tmp_path / "test_strategy" / "latest.json"
    assert latest["backtest_id"] == records[0]["backtest_id"]
    assert latest["metrics"] == report.metrics
    assert "curves" in latest
    assert "curves" not in records[0]
    assert records[0]["trade_export"] is None
    assert not (latest_path.parent / "trades").exists()
    assert not list(latest_path.parent.glob("*.txt"))


def test_save_appends_history_and_optional_exports_have_matching_references(tmp_path) -> None:
    engine = Kijun()
    report = engine.analyze([_trade(18, 20, 2, 1)], metadata={"strategy": "SMA Crossover"})

    latest_path = engine.save(report, output_root=tmp_path, save_trades=True, save_text=True)
    first = load_report(latest_path)
    trade_path = latest_path.parent / first["trade_export"]
    text_path = latest_path.parent / first["text_summary"]
    engine.save(report, output_root=tmp_path, save_trades=True)
    records = load_history_records(latest_path.parent / "history.jsonl")

    assert trade_path.is_file()
    assert "entry_time" in trade_path.read_text(encoding="utf-8")
    assert text_path.is_file()
    assert "Backtest report" in text_path.read_text(encoding="utf-8")
    assert len(records) == 2
    assert records[0]["backtest_id"] != records[1]["backtest_id"]
    assert all(record["trade_export"] for record in records)
    assert records[1]["backtest_id"] == load_report(latest_path)["backtest_id"]


def test_failed_serialization_does_not_replace_latest_or_append_history(
    monkeypatch, tmp_path
) -> None:
    engine = Kijun()
    report = engine.analyze([], metadata={"strategy": "safe write"})
    latest_path = engine.save(report, output_root=tmp_path)
    previous = latest_path.read_bytes()
    history_path = latest_path.parent / "history.jsonl"
    previous_history = history_path.read_bytes()

    def fail_json(*args, **kwargs):
        raise TypeError("simulated JSON serialization failure")

    monkeypatch.setattr(kijun_module.json, "dumps", fail_json)
    with pytest.raises(TypeError, match="simulated"):
        engine.save(report, output_root=tmp_path)

    assert latest_path.read_bytes() == previous
    assert history_path.read_bytes() == previous_history


def test_failed_atomic_replace_keeps_previous_latest(monkeypatch, tmp_path) -> None:
    engine = Kijun()
    report = engine.analyze([], metadata={"strategy": "atomic write"})
    latest_path = engine.save(report, output_root=tmp_path)
    previous = latest_path.read_bytes()
    history_path = latest_path.parent / "history.jsonl"
    previous_history = history_path.read_bytes()
    original_replace = kijun_module.os.replace

    def fail_latest_replace(source, target):
        if Path(target).name == "latest.json":
            raise OSError("simulated interrupted replacement")
        original_replace(source, target)

    monkeypatch.setattr(kijun_module.os, "replace", fail_latest_replace)
    with pytest.raises(OSError, match="interrupted"):
        engine.save(report, output_root=tmp_path)

    assert latest_path.read_bytes() == previous
    assert history_path.read_bytes() == previous_history


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


def test_dashboard_loads_the_selected_saved_report(tmp_path) -> None:
    report_path = tmp_path / "saved-report.json"
    report_path.write_text(
        '{"metadata": {"strategy": "saved run"}, "metrics": {"trade_count": 7}}',
        encoding="utf-8",
    )

    report = load_report(report_path)

    assert report["metadata"]["strategy"] == "saved run"
    assert report["metrics"]["trade_count"] == 7


def test_dashboard_loads_history_without_optional_trade_csv(tmp_path) -> None:
    engine = Kijun()
    report = engine.analyze([], metadata={"strategy": "history test"})
    latest_path = engine.save(report, output_root=tmp_path)
    engine.save(report, output_root=tmp_path)
    history_path = latest_path.parent / "history.jsonl"
    records = load_history_records(history_path)

    historical = load_selected_run(latest_path.parent, records[0]["backtest_id"])

    assert historical["history_only"] is True
    assert historical["metrics"] == report.metrics
    assert historical["curves"]["trades"] == []


def test_dashboard_loads_trade_csv_only_for_the_selected_historical_run(tmp_path) -> None:
    engine = Kijun()
    report = engine.analyze([_trade(18, 20, 2, 1)], metadata={"strategy": "trade history"})
    latest_path = engine.save(report, output_root=tmp_path, save_trades=True)
    first_record = load_history_records(latest_path.parent / "history.jsonl")[0]
    engine.save(report, output_root=tmp_path)

    historical = load_selected_run(latest_path.parent, first_record["backtest_id"])

    assert len(historical["curves"]["trades"]) == 1
    assert historical["curves"]["trades"][0]["net_pnl"] == 18

    (latest_path.parent / first_record["trade_export"]).unlink()
    missing_export = load_selected_run(latest_path.parent, first_record["backtest_id"])
    assert missing_export["curves"]["trades"] == []


def test_dashboard_launcher_uses_saved_report_and_starts_only_when_called(
    monkeypatch, tmp_path
) -> None:
    report = Kijun().analyze([], metadata={"strategy": "launch test"})
    report_path = Kijun().save(report, output_root=tmp_path)
    calls = {"commands": [], "options": []}

    class FakeProcess:
        def poll(self):
            return None

    def fake_popen(command, **options):
        calls["commands"].append(command)
        calls["options"].append(options)
        return FakeProcess()

    class Connected:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(kijun_module, "_available_port", lambda: 8765)
    monkeypatch.setattr(kijun_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(kijun_module.socket, "create_connection", lambda *a, **k: Connected())

    url = Kijun().show_dashboard(report, report_path=report_path)

    assert url == "http://localhost:8765"
    streamlit_command, browser_command = calls["commands"]
    assert calls["options"][0]["env"]["PHYLAX_KIJUN_REPORT"] == str(report_path.resolve())
    assert "run" in streamlit_command
    assert "--server.address=127.0.0.1" in streamlit_command
    assert "--server.headless=true" in streamlit_command
    assert any("kijun_dashboard.py" in argument for argument in streamlit_command)
    chromium_path, browser_profile = kijun_module._portable_chromium_paths()
    assert browser_command[0] == str(chromium_path)
    assert f"--user-data-dir={browser_profile}" in browser_command
    assert url in browser_command
    assert "--new-window" not in browser_command


def test_dashboard_launcher_reports_missing_portable_chromium(monkeypatch, tmp_path) -> None:
    report = Kijun().analyze([])
    missing_chromium = tmp_path / "missing" / "chrome.exe"
    monkeypatch.setattr(
        kijun_module,
        "_portable_chromium_paths",
        lambda: (missing_chromium, tmp_path),
    )

    with pytest.raises(FileNotFoundError, match="Tartarus portable Chromium"):
        Kijun().show_dashboard(report)


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
