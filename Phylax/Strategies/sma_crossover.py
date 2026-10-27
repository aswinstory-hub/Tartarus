"""Long-only SMA crossover strategy and configured backtest entry point."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from Data import DhanClient, Instrument, SQLiteCandleStore
from Engines.buroka import Buroka
from Engines.kijun import Kijun

# Strategy settings
FAST_SMA = 10
SLOW_SMA = 30
LOTS = 1
STOP_LOSS = 0.02
TAKE_PROFIT = 0.04
ENTRY_TTL_BARS = 5

# Backtest settings
START_DATE = date(2022, 1, 1)
END_DATE = date(2026, 1, 1)
INTERVAL = "5"
INITIAL_CAPITAL = 1_000_000
RISK_FREE_RATE = 0.0
LOT_SIZE = 1
PNL_MULTIPLIER = 1.0
FEE_RATE = 0.0
SPREAD_BPS = 0.0
SLIPPAGE_BPS = 0.0
END_POLICY = "leave"

# Data, dashboard, and optional export settings
TATA_STEEL = Instrument("51", "IDX_I", "INDEX", "SENSEX")
DATABASE_PATH: Path | None = None
OPEN_DASHBOARD = True
SAVE_TRADES = False
SAVE_TEXT = False
SAVE_REPORT = False


def calculate_smas(candles, fast_period, slow_period):
    """Add the two trailing simple moving averages used by this strategy."""
    if (
        isinstance(fast_period, bool)
        or not isinstance(fast_period, int)
        or fast_period < 1
        or isinstance(slow_period, bool)
        or not isinstance(slow_period, int)
        or slow_period <= fast_period
    ):
        raise ValueError("SMA periods must be positive integers and slow must be greater than fast")

    data = candles.copy()
    data["fast_sma"] = data["close"].rolling(fast_period).mean()
    data["slow_sma"] = data["close"].rolling(slow_period).mean()
    return data


def run_strategy(
    candles,
    broker=None,
    fast_period=FAST_SMA,
    slow_period=SLOW_SMA,
    lots=LOTS,
    stop_pct=STOP_LOSS,
    target_pct=TAKE_PROFIT,
    entry_ttl_bars=ENTRY_TTL_BARS,
    end_policy=END_POLICY,
    trade_start=None,
    initial_capital=INITIAL_CAPITAL,
    equity_marks=None,
):
    """Run the crossover rules and return Buroka's final result."""
    Buroka.validate_candle_data(candles)
    if broker is None:
        broker = Buroka()
    broker.validate_order_settings(
        lots=lots,
        stop_pct=stop_pct,
        target_pct=target_pct,
        entry_ttl_bars=entry_ttl_bars,
    )
    broker.validate_end_policy(end_policy)
    data = calculate_smas(candles, fast_period, slow_period)

    trade_start_time = pd.Timestamp(trade_start) if trade_start is not None else None
    if trade_start_time is not None:
        if trade_start_time.tzinfo is None:
            trade_start_time = trade_start_time.tz_localize(data.index.tz)
        else:
            trade_start_time = trade_start_time.tz_convert(data.index.tz)

    # Keep the old output-list option for callers; Buroka owns the actual marks.
    if equity_marks is not None and not broker.is_equity_tracking:
        broker.start_equity_tracking(initial_capital, trade_start_time)

    previous_fast = None
    previous_slow = None
    pending_entry_id = None

    for timestamp, candle in data.iterrows():
        broker.process_candle(candle)

        if pending_entry_id is not None and not broker.is_order_pending(pending_entry_id):
            pending_entry_id = None

        fast = candle["fast_sma"]
        slow = candle["slow_sma"]
        before_trade_start = trade_start_time is not None and timestamp < trade_start_time
        if pd.isna(fast) or pd.isna(slow) or before_trade_start:
            previous_fast = fast
            previous_slow = slow
            continue

        has_previous_smas = (
            previous_fast is not None and not pd.isna(previous_fast) and not pd.isna(previous_slow)
        )
        crossed_up = has_previous_smas and previous_fast <= previous_slow and fast > slow
        crossed_down = has_previous_smas and previous_fast >= previous_slow and fast < slow

        if crossed_down:
            if pending_entry_id is not None and broker.is_order_pending(pending_entry_id):
                broker.cancel_order(pending_entry_id)
            pending_entry_id = None
            for position in broker.positions:
                if position.side == "buy":
                    broker.close_position_next_candle(position.position_id)
        elif crossed_up and not broker.positions and not broker.pending_orders:
            close = float(candle["close"])
            pending_entry_id = broker.place_limit_order(
                side="buy",
                entry_price=close,
                stop_loss=close * (1 - stop_pct),
                take_profit=close * (1 + target_pct),
                lots=lots,
                valid_for_bars=entry_ttl_bars,
            )

        previous_fast = float(fast)
        previous_slow = float(slow)

    result = broker.finish_backtest(end_policy)
    if equity_marks is not None:
        equity_marks.extend(result.equity_marks)
    return result


run_backtest = run_strategy


def main():
    # Load warm-up candles as well, but do not allow signals before START_DATE.
    Kijun.validate_run_settings(INITIAL_CAPITAL, RISK_FREE_RATE)
    warmup_start = START_DATE - timedelta(days=SLOW_SMA * 3)
    data_source = SQLiteCandleStore(DATABASE_PATH) if DATABASE_PATH else DhanClient()
    candle_data = data_source.fetch(TATA_STEEL, warmup_start, END_DATE, interval=INTERVAL)
    candles = candle_data.to_ohlc_frame()
    invalid_volume_timestamps = getattr(candle_data, "invalid_volume_timestamps", ())
    if invalid_volume_timestamps:
        print(
            f"Warning: excluded {len(invalid_volume_timestamps)} candle(s) "
            "with negative volume; timestamps are included in report metadata.",
            file=sys.stderr,
        )
    warmup_bars = int((candles.index < pd.Timestamp(START_DATE, tz="Asia/Kolkata")).sum())
    if warmup_bars < SLOW_SMA:
        print(
            f"Warning: only {warmup_bars} candles precede the backtest start; "
            f"{SLOW_SMA} are needed to fully warm the slow SMA.",
            file=sys.stderr,
        )

    # Configure Buroka with the trading costs and contract sizing for this run.
    broker = Buroka(
        lot_size=LOT_SIZE,
        multiplier=PNL_MULTIPLIER,
        fee_rate=FEE_RATE,
        spread_bps=SPREAD_BPS,
        slippage_bps=SLIPPAGE_BPS,
        max_positions=1,
        max_pending_orders=1,
    )
    broker.start_equity_tracking(INITIAL_CAPITAL, START_DATE)

    parameters = {
        "fast_period": FAST_SMA,
        "slow_period": SLOW_SMA,
        "lots": LOTS,
        "stop_pct": STOP_LOSS,
        "target_pct": TAKE_PROFIT,
        "entry_ttl_bars": ENTRY_TTL_BARS,
    }
    result = run_strategy(candles, broker=broker, trade_start=START_DATE)

    # Kijun prepares metadata, metrics, saved reports, and the optional dashboard.
    kijun = Kijun()
    timeframe = "1d" if INTERVAL == "1d" else f"{INTERVAL}m"
    metadata = kijun.strategy_metadata(
        strategy="SMA crossover",
        parameters=parameters,
        instrument=TATA_STEEL.symbol,
        timeframe=timeframe,
        data_source="local SQLite" if DATABASE_PATH else "Dhan historical data",
        start=START_DATE,
        end=END_DATE,
        warmup_start=warmup_start,
        warmup_bars=warmup_bars,
        broker=broker,
        end_policy=END_POLICY,
        initial_capital=INITIAL_CAPITAL,
    )
    if invalid_volume_timestamps:
        metadata["data_quality_warnings"] = {
            "excluded_negative_volume_timestamps": [
                timestamp.isoformat() for timestamp in invalid_volume_timestamps
            ]
        }
    kijun.review_and_save(
        result,
        initial_capital=INITIAL_CAPITAL,
        risk_free_rate=RISK_FREE_RATE,
        metadata=metadata,
        strategy_id="sma_crossover",
        save_trades=SAVE_TRADES or SAVE_REPORT,
        save_text=SAVE_TEXT or SAVE_REPORT,
        dashboard=OPEN_DASHBOARD,
    )


if __name__ == "__main__":
    main()
