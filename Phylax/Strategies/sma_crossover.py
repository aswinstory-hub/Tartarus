"""Long-only SMA crossover example that exercises Buroka's order lifecycle.

Signals use completed candles. A golden cross submits a buy limit at that
candle's close; Buroka can fill it from the next candle onward. A death cross
cancels a pending entry and schedules any open long to close at the next
candle's open. Stop-loss and take-profit brackets remain active between
signals. This is an example strategy, not an investment recommendation.
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from Data import DhanClient, Instrument, SQLiteCandleStore
from Engines.buroka import BrokerSnapshot, Buroka, EndPolicy
from Engines.kijun import Kijun

TATA_STEEL = Instrument(
    security_id="3499",
    exchange_segment="NSE_EQ",
    instrument="EQUITY",
    symbol="TATASTEEL",
)
DEFAULT_INITIAL_CAPITAL = 1_000_000


def run_backtest(
    candles: pd.DataFrame,
    *,
    fast_period: int = 10,
    slow_period: int = 30,
    lots: int = 1,
    stop_pct: float = 0.02,
    target_pct: float = 0.04,
    entry_ttl_bars: int = 5,
    end_policy: EndPolicy = "leave",
    trade_start: date | datetime | pd.Timestamp | None = None,
    broker: Buroka | None = None,
) -> BrokerSnapshot:
    """Run a deterministic, long-only moving-average crossover backtest."""
    if isinstance(fast_period, bool) or not isinstance(fast_period, int) or fast_period < 1:
        raise ValueError("fast_period must be a positive integer")
    if (
        isinstance(slow_period, bool)
        or not isinstance(slow_period, int)
        or slow_period <= fast_period
    ):
        raise ValueError("slow_period must be an integer greater than fast_period")
    if isinstance(lots, bool) or not isinstance(lots, int) or lots < 1:
        raise ValueError("lots must be a positive integer")
    if (
        not math.isfinite(stop_pct)
        or not math.isfinite(target_pct)
        or not 0 < stop_pct < 1
        or not 0 < target_pct
    ):
        raise ValueError("stop_pct must be between 0 and 1 and target_pct must be positive")
    if (
        isinstance(entry_ttl_bars, bool)
        or not isinstance(entry_ttl_bars, int)
        or entry_ttl_bars < 1
    ):
        raise ValueError("entry_ttl_bars must be a positive integer")
    required = {"open", "high", "low", "close"}
    missing = required - set(candles.columns)
    if missing:
        raise ValueError(f"candles missing columns: {', '.join(sorted(missing))}")
    if not isinstance(candles.index, pd.DatetimeIndex) or candles.index.tz is None:
        raise ValueError("candles must have a timezone-aware DatetimeIndex")
    if not candles.index.is_monotonic_increasing or candles.index.has_duplicates:
        raise ValueError("candle timestamps must be strictly increasing and unique")
    if candles[list(required)].isna().any().any():
        raise ValueError("candles must not contain missing OHLCV values")

    data = candles.copy()
    data["sma_fast"] = data["close"].rolling(fast_period, min_periods=fast_period).mean()
    data["sma_slow"] = data["close"].rolling(slow_period, min_periods=slow_period).mean()
    first_trade_timestamp = _as_index_timestamp(trade_start, data.index) if trade_start else None
    active_broker = broker or Buroka()
    pending_entry_id: str | None = None
    prior_fast: float | None = None
    prior_slow: float | None = None

    for timestamp, candle in data.iterrows():
        # 1. Let Buroka handle existing orders and positions on this candle.
        active_broker.process_candle(candle)
        current_fast = candle["sma_fast"]
        current_slow = candle["sma_slow"]
        if pd.isna(current_fast) or pd.isna(current_slow):
            continue
        current_fast, current_slow = float(current_fast), float(current_slow)
        # 2. Warm-up candles build averages, but cannot create trades.
        if first_trade_timestamp is not None and timestamp < first_trade_timestamp:
            prior_fast, prior_slow = current_fast, current_slow
            continue
        # 3. Compare the averages on this candle with the previous candle.
        crossed_up = (
            prior_fast is not None
            and prior_slow is not None
            and prior_fast <= prior_slow
            and current_fast > current_slow
        )
        crossed_down = (
            prior_fast is not None
            and prior_slow is not None
            and prior_fast >= prior_slow
            and current_fast < current_slow
        )
        if crossed_down:
            # 4. A downward cross cancels an unfilled entry and exits a long.
            if pending_entry_id is not None:
                if any(
                    order.order_id == pending_entry_id for order in active_broker.pending_orders
                ):
                    active_broker.cancel_order(pending_entry_id)
                pending_entry_id = None
            for position in active_broker.positions:
                if position.side == "buy":
                    active_broker.close_position_next_candle(position.position_id)
        elif crossed_up and not active_broker.positions and not active_broker.pending_orders:
            # 5. An upward cross enters at this close; Buroka may fill next candle.
            close = float(candle["close"])
            pending_entry_id = active_broker.place_limit_order(
                side="buy",
                entry_price=close,
                stop_loss=close * (1 - stop_pct),
                take_profit=close * (1 + target_pct),
                lots=lots,
                valid_for_bars=entry_ttl_bars,
            )
        if pending_entry_id is not None and not any(
            order.order_id == pending_entry_id for order in active_broker.pending_orders
        ):
            pending_entry_id = None
        prior_fast, prior_slow = current_fast, current_slow

    # 6. Return completed trades and any open or pending state.
    return active_broker.finish_backtest(end_policy)


def _as_index_timestamp(
    value: date | datetime | pd.Timestamp, index: pd.DatetimeIndex
) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if index.tz is None:
        raise ValueError("candles must have a timezone-aware DatetimeIndex")
    if timestamp.tzinfo is None:
        return timestamp.tz_localize(index.tz)
    return timestamp.tz_convert(index.tz)


def _engine_candles(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert the Data module's display columns to Buroka's OHLC column names."""
    result = frame.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    ).copy()
    return result.drop(columns=["Date", "Time"], errors="ignore")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TATA STEEL SMA crossover backtest")
    parser.add_argument(
        "--start", type=date.fromisoformat, required=True, help="Inclusive date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end", type=date.fromisoformat, required=True, help="Exclusive date (YYYY-MM-DD)"
    )
    parser.add_argument("--fast", type=int, default=10, help="Fast SMA period")
    parser.add_argument("--slow", type=int, default=30, help="Slow SMA period")
    parser.add_argument("--lots", type=int, default=1, help="Number of lots per entry")
    parser.add_argument("--lot-size", type=int, default=1, help="Units per lot")
    parser.add_argument("--multiplier", type=float, default=1.0, help="P&L multiplier per unit")
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=DEFAULT_INITIAL_CAPITAL,
        help="Starting account capital for Kijun return metrics; not used for position sizing",
    )
    parser.add_argument("--stop-pct", type=float, default=0.02, help="Stop distance fraction")
    parser.add_argument("--target-pct", type=float, default=0.04, help="Target distance fraction")
    parser.add_argument(
        "--entry-ttl-bars", type=int, default=5, help="Eligible candles before entry expires"
    )
    parser.add_argument(
        "--end-policy",
        choices=("leave", "cancel_pending", "close_at_last_close"),
        default="leave",
        help="How Buroka handles pending entries/open positions at end of data",
    )
    parser.add_argument("--fee-rate", type=float, default=0.0, help="Per-side fee rate as decimal")
    parser.add_argument(
        "--spread-bps", type=float, default=0.0, help="Full quoted spread in basis points"
    )
    parser.add_argument(
        "--slippage-bps", type=float, default=0.0, help="Per-side slippage cost in basis points"
    )
    parser.add_argument(
        "--db", type=Path, help="Read candles from a local SQLite file instead of Dhan"
    )
    args = parser.parse_args()
    if args.start >= args.end:
        parser.error("--start must be earlier than the exclusive --end")
    if args.fast < 1 or args.slow <= args.fast:
        parser.error("--fast must be positive and --slow must be greater than --fast")
    if not math.isfinite(args.initial_capital) or args.initial_capital <= 0:
        parser.error("--initial-capital must be finite and positive")
    warmup_start = args.start - timedelta(days=args.slow * 3)
    source = SQLiteCandleStore(args.db) if args.db else DhanClient()
    candles = source.fetch(TATA_STEEL, warmup_start, args.end, interval="1d")
    frame = _engine_candles(candles.frame)
    start_timestamp = _as_index_timestamp(args.start, frame.index)
    warmup_bar_count = int((frame.index < start_timestamp).sum())
    if warmup_bar_count < args.slow:
        print(
            f"Warning: only {warmup_bar_count} candles precede the backtest start; "
            f"{args.slow} are needed to fully warm the slow SMA.",
            file=sys.stderr,
        )
    broker = Buroka(
        lot_size=args.lot_size,
        multiplier=args.multiplier,
        fee_rate=args.fee_rate,
        spread_bps=args.spread_bps,
        slippage_bps=args.slippage_bps,
        max_positions=1,
        max_pending_orders=1,
    )
    result = run_backtest(
        frame,
        fast_period=args.fast,
        slow_period=args.slow,
        lots=args.lots,
        stop_pct=args.stop_pct,
        target_pct=args.target_pct,
        entry_ttl_bars=args.entry_ttl_bars,
        end_policy=args.end_policy,
        trade_start=args.start,
        broker=broker,
    )
    report_engine = Kijun()
    report = report_engine.review(
        result,
        initial_capital=args.initial_capital,
        metadata={
            "strategy": "SMA crossover",
            "parameters": {
                "fast_period": args.fast,
                "slow_period": args.slow,
                "lots": args.lots,
                "stop_pct": args.stop_pct,
                "target_pct": args.target_pct,
                "entry_ttl_bars": args.entry_ttl_bars,
            },
            "instrument": TATA_STEEL.symbol,
            "timeframe": "1d",
            "data_source": "local SQLite" if args.db else "Dhan historical data",
            "data_range": {
                "start_inclusive": args.start.isoformat(),
                "end_exclusive": args.end.isoformat(),
            },
            "warmup_data": {
                "requested_start": warmup_start.isoformat(),
                "bars_before_backtest_start": warmup_bar_count,
                "signals_enabled_from": args.start.isoformat(),
            },
            "costs_and_fill_assumptions": {
                "fee_rate": args.fee_rate,
                "spread_bps": args.spread_bps,
                "slippage_bps": args.slippage_bps,
                "fill_timing": "orders first eligible on the next candle",
                "end_of_data": args.end_policy,
            },
            "broker_settings": {
                "lots_per_entry": args.lots,
                "lot_size": args.lot_size,
                "pnl_multiplier": args.multiplier,
                "max_positions": 1,
                "max_pending_orders": 1,
                "initial_capital_for_metrics": args.initial_capital,
            },
        },
    )
    report_engine.print_summary(report)
    stamp = report.generated_at.replace(":", "").replace("-", "")
    saved_paths = report_engine.save(
        report, stem=f"sma-crossover-{args.start}-{args.end}-{stamp}"
    )
    if saved_paths is None:
        report_engine.show_dashboard(report)
    else:
        json_path, _, _ = saved_paths
        report_engine.show_dashboard(report, report_path=json_path)
    print(f"Pending orders at end: {len(result.pending_orders)}")
    print(f"Open positions at end: {len(result.positions)}")
    print(
        "Costs per Buroka settings: "
        f"fee rate={args.fee_rate}, spread={args.spread_bps} bps, "
        f"slippage={args.slippage_bps} bps"
    )


if __name__ == "__main__":
    main()
