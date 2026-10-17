# Buroka — Broker Simulation Engine

Simulate pending limit orders, fills, SL/TP exits, positions and trade results in historical backtests. Never place live orders.

Order input:
```python
{
    "side": "buy",  # or "sell"
    "entry_price": 100.0,
    "sl": 98.0,
    "tp": 104.0,
    "lots": 1
}
```
Illustrative schema only; market entries are unsupported. Validate side, numeric fields, price relationships, quantity and instrument-specific lot conversion.

The strategy passes each current candle to Buroka on each iteration. Buroka updates existing orders/positions under a documented model. The strategy then evaluates available information and may submit new limit orders. Define call order explicitly to avoid look-ahead.

Before implementation, specify limit fill/gap behavior, SL/TP collisions, entry-candle exits, fees/taxes/spread/slippage, lot conversion/multiplier, pending expiry/cancellation, duplicates, end-of-data state, shorting/margin and output schema. OHLC does not reveal intrabar order; document conservative assumptions and test edge cases.
