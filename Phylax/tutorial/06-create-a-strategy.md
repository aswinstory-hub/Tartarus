# Tutorial 6: Create a Strategy

Start from [`Strategies/framework.md`](../Strategies/framework.md) and inspect [`Strategies/sma_crossover.py`](../Strategies/sma_crossover.py). A strategy decides when to trade; Buroka tracks simulated orders; Kijun evaluates results.

## Keep the steps readable

1. State the hypothesis and write exact entry and exit rules in comments or module documentation.
2. Put parameters together near the start of the strategy file.
3. Load candles using `Data`; record instrument, timeframe, dates, and source.
4. Calculate indicators from current and past observations. Fetch enough earlier candles for warm-up, but exclude them from scored trades.
5. For each candle, call `broker.process_candle(candle)` first.
6. Check the signal and tell Buroka what to do. Orders submitted now are eligible on a later candle.
7. Choose how pending orders and open positions are handled at the end of the data.
8. Send Buroka results and periodic marked equity (when calculated) to Kijun. Save the report and record assumptions.

## Example of a clear signal check

```python
crossed_up = (
    previous_fast is not None
    and previous_fast <= previous_slow
    and fast_average > slow_average
)

if crossed_up and not broker.positions and not broker.pending_orders:
    broker.place_limit_order(
        side="buy",
        entry_price=float(candle["Close"]),
        stop_loss=float(candle["Close"]) * 0.98,
        take_profit=float(candle["Close"]) * 1.04,
        lots=1,
    )
```

This is an illustrative SMA-style condition, not a complete strategy. Update `previous_fast` and `previous_slow` after evaluating the current candle, and ensure they refer only to earlier observations. Follow the full framework example for finalization and reporting.

## Before trusting a result

Document and validate the data range, timestamp and candle timing, warm-up, fill behavior, stop/target collisions, fees, spread, slippage, position sizing, and end-of-data handling. Add tests for signal boundaries and execution timing when changing strategy behavior. Historical performance does not establish future performance. The authoritative module and integrity notes are in [`docs/`](../docs/README.md) and [`SANDBOX.md`](../SANDBOX.md).
