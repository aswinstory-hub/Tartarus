# Buroka Broker Simulator

Buroka is a local simulated broker implemented in [`Engines/buroka.py`](../Engines/buroka.py). It tracks pending limit entries, open positions, requested signal exits, and completed trades. It has no live broker connection.

## Processing order

For each completed candle, Buroka checks existing positions for stop/target exits, executes requested signal exits at the candle open, then checks pending limit orders against the candle range. After `process_candle` returns, the strategy may evaluate that completed candle and submit an order. Such an order first becomes eligible on the following candle. This separation is important for avoiding same-candle look-ahead.

## Limit order inputs

The readable entry method is `place_limit_order(side, entry_price, stop_loss, take_profit, lots, valid_for_bars=None)`. A buy requires `stop_loss < entry_price < take_profit`; a sell requires `take_profit < entry_price < stop_loss`. Prices must be finite and positive, and lots and any validity duration must be positive integers. Invalid orders raise an error.

Only limit entries are supported. Pending orders can be cancelled. The engine rejects exact duplicate requests while the matching request is pending or open and applies configurable limits to open positions and pending orders. There are no partial fills, tick rounding, leverage, margin, or financing model.

## Execution assumptions

The fill rule, open-price improvement, stop/target collision behavior, gap handling, and costs are documented in the authoritative [Buroka specification](../Engines/BUROKA.md). These are deterministic OHLC approximations: the true intrabar order and queue position cannot be reconstructed from candles. Fees, spread, and slippage default to zero and must be explicitly configured from justified assumptions.

## End-of-data and outputs

`finish_backtest` returns a snapshot. The default `leave` policy preserves open positions and pending orders without inventing closing fills. Alternatives cancel pending orders or close remaining positions at the final close. A completed trade includes timestamps, prices, sizing, gross P&L, costs, net P&L, identifiers, and exit reason. `mark_to_market_equity` estimates account value for one instrument at a supplied price; it is not a cash, margin, or portfolio ledger.

See [Tutorial 3: Buroka](../tutorial/03-buroka.md) and [Engines/BUROKA.md](../Engines/BUROKA.md).
