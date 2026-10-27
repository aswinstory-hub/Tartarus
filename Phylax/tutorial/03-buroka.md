# Tutorial 3: Use Buroka

Buroka is the simulated broker in `Engines/buroka.py`. It manages limit orders and positions over historical candles. It never sends orders to Dhan or any other broker.

## Basic loop

```python
from Engines import Buroka

broker = Buroka()

for timestamp, candle in frame.iterrows():
    # First let the simulator process existing state on this completed candle.
    broker.process_candle(candle)

    # Put your signal check here. It can use this candle and earlier candles.
    if signal_is_true:
        broker.place_limit_order(
            side="buy",
            entry_price=float(candle["Close"]),
            stop_loss=float(candle["Close"]) * 0.98,
            take_profit=float(candle["Close"]) * 1.04,
            lots=1,
        )

results = broker.finish_backtest("leave")
print(results.trades)
print(results.pending_orders)
print(results.positions)
```

The example uses title-case Data columns for prices; adapt the column name if your frame uses lowercase names. A limit order submitted after processing the current candle can fill starting on the next candle. This prevents using the candle's completed high/low to create and fill a new decision retroactively.

## Manage exits and inspect results

Attach stop-loss and take-profit values to the entry order. For a long buy, the stop must be below entry and target above; for a short sell, the target must be below entry and stop above. For a signal-based close, call `close_position_next_candle(position_id)`; it executes at the next processed candle open. The `leave` finalization policy keeps unfinished orders and positions visible. Other policies are described in [Buroka reference](../docs/buroka.md).

Fees, spread, and slippage default to zero. Set values only from explicit assumptions. OHLC cannot reveal the intrabar price path, so Buroka applies documented deterministic collision and gap rules rather than claiming exchange-accurate fills.
