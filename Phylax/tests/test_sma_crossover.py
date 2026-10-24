from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

import Strategies.sma_crossover as strategy
from Engines.buroka import Buroka
from Strategies.sma_crossover import run_backtest


def toy_candles(closes: list[float]) -> pd.DataFrame:
    """Tiny deterministic unit-test sequence; it is not market data."""
    index = pd.date_range("2024-01-01 09:15", periods=len(closes), freq="D", tz="Asia/Kolkata")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [value + 1 for value in closes],
            "low": [value - 1 for value in closes],
            "close": closes,
            "volume": [1000] * len(closes),
        },
        index=index,
    )


def test_sma_cross_submits_next_candle_limit_and_closes_on_bear_cross() -> None:
    broker = Buroka()
    result = run_backtest(
        toy_candles([10, 9, 8, 7, 8, 9, 10, 9, 8, 7]),
        fast_period=2,
        slow_period=3,
        stop_pct=0.5,
        target_pct=0.5,
        broker=broker,
    )

    trade = result.trades[0]
    assert trade.entry_time == pd.Timestamp("2024-01-07 09:15", tz="Asia/Kolkata")
    assert trade.exit_time == pd.Timestamp("2024-01-10 09:15", tz="Asia/Kolkata")
    assert trade.exit_price == 7
    assert trade.exit_reason == "signal"
    assert not result.positions


def test_sma_strategy_rejects_invalid_parameters_and_duplicate_times() -> None:
    candles = toy_candles([10, 9, 8, 7])
    with pytest.raises(ValueError, match="greater than"):
        run_backtest(candles, fast_period=3, slow_period=3)
    candles.index = [candles.index[0]] * len(candles)
    with pytest.raises(ValueError, match="strictly increasing"):
        run_backtest(candles)


def test_sma_strategy_applies_explicit_close_at_end_policy() -> None:
    result = run_backtest(
        toy_candles([10, 9, 8, 7, 8, 9, 10, 10.5]),
        fast_period=2,
        slow_period=3,
        stop_pct=0.5,
        target_pct=0.5,
        end_policy="close_at_last_close",
    )

    assert not result.positions
    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "end_of_data"
    assert result.trades[0].exit_price == 10.5


def test_sma_warmup_updates_indicators_without_trading_before_start() -> None:
    candles = toy_candles([10, 9, 8, 7, 8, 9, 10, 10.5])
    result = run_backtest(
        candles,
        fast_period=2,
        slow_period=3,
        stop_pct=0.5,
        target_pct=0.5,
        trade_start=candles.index[5],
        end_policy="close_at_last_close",
    )

    assert len(result.trades) == 1
    assert result.trades[0].entry_time == candles.index[6]
    assert result.trades[0].entry_time >= candles.index[5]


def test_cli_uses_million_initial_capital_and_always_opens_dashboard(monkeypatch) -> None:
    calls = {"initial_capital": None, "dashboard": 0}

    class FakeDataSource:
        def fetch(self, instrument, start, end, *, interval):
            return SimpleNamespace(frame=toy_candles([10, 9, 8, 7, 8, 9, 10, 10.5]))

    class FakeKijun:
        def review(self, result, *, initial_capital, metadata):
            calls["initial_capital"] = initial_capital
            return SimpleNamespace(generated_at="2025-01-01T00:00:00+00:00")

        def print_summary(self, report):
            pass

        def save(self, report, *, stem):
            pass

        def show_dashboard(self, report):
            calls["dashboard"] += 1

    monkeypatch.setattr(strategy, "DhanClient", FakeDataSource)
    monkeypatch.setattr(strategy, "Kijun", FakeKijun)
    monkeypatch.setattr(
        "sys.argv",
        [
            "sma_crossover",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-09",
            "--fast",
            "2",
            "--slow",
            "3",
        ],
    )

    strategy.main()

    assert calls == {"initial_capital": 1_000_000, "dashboard": 1}
