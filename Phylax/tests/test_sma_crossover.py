from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

import Strategies.sma_crossover as strategy
from Engines.buroka import Buroka, OrderStatus
from Engines.kijun import Kijun
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
    assert trade.entry_price == 9  # next candle opened below the buy limit at 10
    assert trade.exit_time == pd.Timestamp("2024-01-10 09:15", tz="Asia/Kolkata")
    assert trade.exit_price == 7
    assert trade.quantity == 1
    assert trade.gross_pnl == -2
    assert trade.costs == 0
    assert trade.net_pnl == -2
    assert trade.exit_reason == "signal"
    assert not result.positions


def test_sma_strategy_keeps_candle_data_checks() -> None:
    candles = toy_candles([10, 9, 8, 7])
    with pytest.raises(ValueError, match="missing columns"):
        run_backtest(candles.drop(columns="close"))

    candles.index = [candles.index[0]] * len(candles)
    with pytest.raises(ValueError, match="strictly increasing"):
        run_backtest(candles)

    with pytest.raises(ValueError, match="empty"):
        run_backtest(toy_candles([]))

    candles = toy_candles([10, 9, 8, 7])
    candles.iloc[1, candles.columns.get_loc("close")] = float("nan")
    with pytest.raises(ValueError, match="finite and complete"):
        run_backtest(candles)


def test_strategy_rejects_invalid_parameters() -> None:
    candles = toy_candles([10, 9, 8, 7])
    with pytest.raises(ValueError, match="greater than"):
        run_backtest(candles, fast_period=3, slow_period=3)
    with pytest.raises(ValueError, match="positive integer"):
        run_backtest(candles, lots=0)
    with pytest.raises(ValueError, match="stop_pct"):
        run_backtest(candles, stop_pct=1.0)
    with pytest.raises(ValueError, match="entry_ttl_bars"):
        run_backtest(candles, entry_ttl_bars=0)


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


def test_death_cross_cancels_a_pending_entry() -> None:
    broker = Buroka()
    result = run_backtest(
        toy_candles([40, 8, 12, 9, 11]),
        fast_period=2,
        slow_period=3,
        stop_pct=0.5,
        target_pct=0.5,
        entry_ttl_bars=5,
        broker=broker,
    )

    assert broker.order_history[0].status == OrderStatus.CANCELLED
    assert len(result.trades) == 0
    assert len(result.pending_orders) == 0
    assert len(result.positions) == 0


def test_expired_entry_does_not_block_a_later_golden_cross() -> None:
    broker = Buroka()
    result = run_backtest(
        toy_candles([10, 9, 8, 7, 8, 9, 15, 8, 7, 6, 7, 8]),
        fast_period=2,
        slow_period=3,
        stop_pct=0.5,
        target_pct=0.5,
        entry_ttl_bars=1,
        broker=broker,
    )

    orders = broker.order_history
    assert len(orders) == 2
    assert orders[0].status == OrderStatus.EXPIRED
    assert orders[1].status == OrderStatus.PENDING
    assert len(result.pending_orders) == 1


def test_refactor_keeps_trade_records_and_kijun_equity_metrics() -> None:
    closes = [10, 9, 8, 7, 8, 9, 10, 9, 8, 7, 8, 9, 12, 8, 7, 6, 7, 8]
    candles = toy_candles(closes)
    legacy_marks = []
    result = run_backtest(
        candles,
        broker=Buroka(fee_rate=0.001, spread_bps=2, slippage_bps=3),
        fast_period=2,
        slow_period=3,
        lots=2,
        stop_pct=0.3,
        target_pct=0.4,
        entry_ttl_bars=2,
        end_policy="close_at_last_close",
        trade_start=candles.index[4],
        initial_capital=100_000,
        equity_marks=legacy_marks,
    )

    trade_results = [
        (trade.entry_time, trade.exit_time, trade.entry_price, trade.exit_price,
         trade.gross_pnl, trade.costs, trade.net_pnl, trade.exit_reason)
        for trade in result.trades
    ]
    assert trade_results == [
        (candles.index[6], candles.index[9], 9.0, 6.3, -5.4, 0.04284, -5.44284, "stop_loss"),
        (
            candles.index[13],
            candles.index[14],
            8.0,
            6.3,
            -3.4000000000000004,
            0.04004,
            -3.44004,
            "stop_loss",
        ),
    ]
    assert legacy_marks == list(result.equity_marks)

    old_report = Kijun().analyze(
        result.trades,
        initial_capital=100_000,
        periodic_equity=pd.Series(
            [value for _, value in legacy_marks],
            index=pd.DatetimeIndex([stamp for stamp, _ in legacy_marks]),
        ),
    )
    new_report = Kijun().review(result, initial_capital=100_000)
    assert new_report.metrics == old_report.metrics
    assert new_report.curves == old_report.curves



@pytest.mark.parametrize(
    ("save_report", "save_text", "save_trades", "open_dashboard"),
    [
        (False, False, False, False),
        (True, False, False, False),
        (False, True, False, False),
        (False, False, True, False),
        (False, False, False, True),
    ],
)
@pytest.mark.parametrize(("interval", "timeframe"), [("1d", "1d"), ("5", "5m")])
def test_main_uses_settings_and_saves_report(
    monkeypatch, save_report, save_text, save_trades, open_dashboard, interval, timeframe
) -> None:
    calls = {}

    class FakeDataSource:
        def fetch(self, instrument, start, end, *, interval):
            calls["fetch"] = (instrument, start, end, interval)
            frame = toy_candles([10, 9, 8, 7, 8, 9, 10, 10.5])
            return SimpleNamespace(
                source="fixture",
                to_ohlc_frame=lambda: frame,
            )

    class FakeKijun:
        @staticmethod
        def validate_run_settings(initial_capital, risk_free_rate):
            calls["validated"] = (initial_capital, risk_free_rate)

        def strategy_metadata(self, **values):
            calls["metadata"] = values
            return {"strategy": values["strategy"]}

        def review_and_save(
            self,
            result,
            *,
            initial_capital,
            risk_free_rate,
            metadata,
            strategy_id,
            save_trades,
            save_text,
            dashboard,
        ):
            calls["result"] = result
            calls["report_run"] = (
                initial_capital,
                risk_free_rate,
                metadata,
                strategy_id,
                save_trades,
                save_text,
                dashboard,
            )

    monkeypatch.setattr(strategy, "DhanClient", FakeDataSource)
    monkeypatch.setattr(strategy, "Kijun", FakeKijun)
    monkeypatch.setattr(strategy, "START_DATE", strategy.date(2024, 1, 1))
    monkeypatch.setattr(strategy, "END_DATE", strategy.date(2024, 1, 9))
    monkeypatch.setattr(strategy, "INTERVAL", interval)
    monkeypatch.setattr(strategy, "FAST_SMA", 2)
    monkeypatch.setattr(strategy, "SLOW_SMA", 3)
    monkeypatch.setattr(strategy, "SAVE_REPORT", save_report)
    monkeypatch.setattr(strategy, "SAVE_TEXT", save_text)
    monkeypatch.setattr(strategy, "SAVE_TRADES", save_trades)
    monkeypatch.setattr(strategy, "OPEN_DASHBOARD", open_dashboard)

    strategy.main()

    start = strategy.date(2024, 1, 1)
    end = strategy.date(2024, 1, 9)
    assert calls["fetch"][1:] == (start - strategy.timedelta(days=9), end, interval)
    assert calls["validated"] == (1_000_000, 0.0)
    assert len(calls["result"].equity_marks) == 8
    assert calls["report_run"][0:2] == (1_000_000, 0.0)
    assert calls["report_run"][3:] == (
        "sma_crossover",
        save_trades or save_report,
        save_text or save_report,
        open_dashboard,
    )
    assert calls["metadata"]["warmup_bars"] == 0
    assert calls["metadata"]["timeframe"] == timeframe
    assert calls["metadata"]["parameters"] == {
        "fast_period": 2,
        "slow_period": 3,
        "lots": 1,
        "stop_pct": 0.02,
        "target_pct": 0.04,
        "entry_ttl_bars": 5,
    }


def test_main_does_not_save_a_backtest_that_fails(monkeypatch) -> None:
    calls = {"save": 0, "dashboard": 0}

    class FakeDataSource:
        def fetch(self, instrument, start, end, *, interval):
            frame = toy_candles([10, 9, 8, 7, 8, 9, 10, 10.5])
            return SimpleNamespace(source="fixture", to_ohlc_frame=lambda: frame)

    class FakeKijun:
        @staticmethod
        def validate_run_settings(initial_capital, risk_free_rate):
            pass

        def strategy_metadata(self, **values):
            return {}

        def review_and_save(self, *args, **kwargs):
            calls["dashboard"] += 1

    def fail_backtest(*args, **kwargs):
        raise RuntimeError("simulated backtest failure")

    monkeypatch.setattr(strategy, "DhanClient", FakeDataSource)
    monkeypatch.setattr(strategy, "Kijun", FakeKijun)
    monkeypatch.setattr(strategy, "run_strategy", fail_backtest)

    with pytest.raises(RuntimeError, match="simulated backtest failure"):
        strategy.main()

    assert calls == {"save": 0, "dashboard": 0}


def test_main_reports_excluded_bad_volume_candles(monkeypatch, capsys) -> None:
    bad_timestamp = pd.Timestamp("2024-01-02 12:50", tz="Asia/Kolkata")
    calls = {}

    class FakeDataSource:
        def fetch(self, instrument, start, end, *, interval):
            return SimpleNamespace(
                source="fixture",
                invalid_volume_timestamps=(bad_timestamp,),
                to_ohlc_frame=lambda: toy_candles(
                    [10, 9, 8, 7, 8, 9, 10, 10.5]
                ),
            )

    class FakeKijun:
        @staticmethod
        def validate_run_settings(initial_capital, risk_free_rate):
            pass

        def strategy_metadata(self, **values):
            return {"strategy": values["strategy"]}

        def review_and_save(self, result, **values):
            calls["metadata"] = values["metadata"]

    monkeypatch.setattr(strategy, "DhanClient", FakeDataSource)
    monkeypatch.setattr(strategy, "Kijun", FakeKijun)
    monkeypatch.setattr(strategy, "START_DATE", strategy.date(2024, 1, 1))
    monkeypatch.setattr(strategy, "END_DATE", strategy.date(2024, 1, 9))
    monkeypatch.setattr(strategy, "FAST_SMA", 2)
    monkeypatch.setattr(strategy, "SLOW_SMA", 3)
    monkeypatch.setattr(strategy, "OPEN_DASHBOARD", False)

    strategy.main()

    assert "excluded 1 candle(s) with negative volume" in capsys.readouterr().err
    assert calls["metadata"]["data_quality_warnings"] == {
        "excluded_negative_volume_timestamps": [bad_timestamp.isoformat()]
    }
