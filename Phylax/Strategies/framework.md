# Strategy backtest file framework

Use this structure when adding a strategy under `Strategies/`. Keep the
strategy logic in its own runnable Python module. The strategy owns its signal
rules and parameters; Buroka owns simulated order state; Kijun owns realized
performance reporting. Strategies that report risk ratios should also record
periodic marked-to-market account equity.

## Required sections

1. **Hypothesis and rules:** state the entry, exit, and risk rules precisely.
2. **Instrument and data:** identify symbol/security ID, timeframe, source,
   requested date range, timezone, gaps, and missing-data behavior.
3. **Parameters:** centralize signal periods, lots, lot size, multiplier, stops,
   targets, costs, and optional starting capital.
4. **Warm-up and validation:** fetch enough candles before the scored range to
   initialize rolling indicators; validate ordered, unique, timezone-aware
   candles and calculate features from current and past candles only.
5. **Simulation loop:** pass every completed candle, including warm-up candles,
   to `broker.process_candle(candle)` before evaluating a signal. Suppress
   orders before the scored start. Call `broker.start_equity_tracking` before
   the loop to collect the previous-candle baseline and each scored close.
   A limit order submitted after candle processing is first eligible on the
   next candle.
6. **Finalization and reporting:** select an explicit end-of-data policy, pass
   completed trades to Kijun, include run metadata, print and save the report.
7. **Tests and limits:** cover signals, order timing, parameters, edge cases,
   data boundaries, and the assumptions the OHLC simulator cannot model.

## Engine settings

Construct Buroka with explicit settings for:

- `lot_size` and `multiplier`, which define quantity and P&L units.
- `fee_rate`, `spread_bps`, and `slippage_bps`, based on sourced assumptions.
- `max_positions` and `max_pending_orders`, based on the strategy rules.

Costs default to zero in the engine. Keep them at zero only when that is the
chosen assumption, and record it in run metadata. Do not invent broker fees,
taxes, fills, or market-data values. `initial_capital` provides Buroka's equity
baseline and Kijun's return basis; it does not set Buroka's position size,
cash balance, margin, or risk limits.

## Strategy module skeleton

Keep the main loop in plain steps: process the candle, check the signal, tell
Buroka what to do, then move to the next candle. The SMA example in
`sma_crossover.py` follows this sequence.

```python
import pandas as pd

from Engines import Buroka, Kijun

broker = Buroka()
initial_capital = 1_000_000
broker.start_equity_tracking(initial_capital, backtest_start)
previous_fast = None
previous_slow = None

for timestamp, candle in candles.iterrows():
    # 1. Update orders and positions using this completed candle.
    broker.process_candle(candle)

    # 2. Read only the indicator values for this candle and earlier candles.
    fast = candle["fast_average"]
    slow = candle["slow_average"]
    if fast is None or slow is None:
        continue

    crossed_up = (
        previous_fast is not None
        and previous_fast <= previous_slow
        and fast > slow
    )

    # 3. Place a limit entry after the signal. It can fill next candle onward.
    if crossed_up and not broker.positions and not broker.pending_orders:
        broker.place_limit_order(
            side="buy",
            entry_price=float(candle["close"]),
            stop_loss=float(candle["close"]) * 0.98,
            take_profit=float(candle["close"]) * 1.04,
            lots=1,
        )

    previous_fast = fast
    previous_slow = slow

# 4. Finish without inventing an end-of-data fill.
results = broker.finish_backtest("leave")

# 5. Ask Kijun to summarize Buroka's results.
report = Kijun().review(
    results,
    initial_capital=initial_capital,
    periods_per_year=252,
    risk_free_rate=0.0,
    metadata={"strategy": "Example"},
)
Kijun().print_summary(report)
```

This is a flow example; the strategy must calculate the example averages and
apply its own date/warm-up rules before the loop. Buroka processes a candle
before the strategy sees its completed-candle signal, and an order submitted
after that processing cannot fill until a later candle. Trade-quality metrics
use closed trades; a marked-equity series includes open positions at each mark.
`finish_backtest("leave")` keeps open positions and pending orders
visible instead of fabricating end-of-data fills. Include a baseline at the
last candle before the scored range when available; Buroka does this when
equity tracking starts before the trading date. With periodic marks, Kijun's
headline return, equity, drawdown,
Sharpe, and Sortino use marked account equity; closed-trade P&L remains separate.

## Report metadata

Include at least the strategy name and parameters, instrument, timeframe,
source, data range (`start_inclusive` and `end_exclusive`), costs, fill timing,
lot conversion, multiplier, and end-of-data policy. Kijun uses the explicit
metadata data range for annualization when present. Supply a positive
`initial_capital` only when its currency and meaning are known. For the runnable
SMA example, see `sma_crossover.py` and `HOWTOUSE.md` at the repository root.
