# Buroka — Broker Simulation Engine

Buroka is a local historical limit-order simulator. It has no live broker
connection and never places real orders. The Python implementation is
`Engines/buroka.py`.

## Candle and strategy loop

Candles must contain numeric `open`, `high`, `low`, and `close` prices and a
timezone-aware timestamp. Timestamps must be strictly increasing. Buroka
processes each completed candle in this order:

1. Update existing positions for stop-loss and take-profit exits.
2. Execute previously requested signal exits at this candle's open.
3. Process pending limit entries against this candle's OHLC range.
4. Return control to the strategy, which may evaluate the completed candle and
   submit new orders.

An order submitted after step 3 is first eligible on the next candle. A caller
may pre-submit orders before the first candle; those are eligible on the first
processed candle. Signal calculations must use only candles already processed.

## Order input and validation

```python
{
    "side": "buy",  # or "sell"
    "entry_price": 100.0,
    "sl": 98.0,
    "tp": 104.0,
    "lots": 1,
    "valid_for_bars": 5,  # optional
}
```

Only limit entries are supported. Prices must be finite and positive. `lots`
must be a positive integer. A buy requires `sl < entry_price < tp`; a sell
requires `tp < entry_price < sl`. `valid_for_bars`, when supplied, must be a
positive integer and counts eligible candles, including the first one. Invalid
orders raise `InvalidOrderError`; they are not silently discarded.

The default broker permits one open position and 20 pending orders; both limits
are configurable. Exact duplicate requests are rejected while the matching
request is pending or its position is open. `cancel_order` cancels a pending
entry. There are no partial fills, tick-size rounding, margin checks, leverage,
or financing charges.

## Fill and exit assumptions

- A buy limit is touched when `low <= entry_price`; a sell limit when
  `high >= entry_price`.
- If the candle opens through a buy limit below its price, the fill uses the
  open for price improvement. A sell limit opening above its price is handled
  symmetrically. Otherwise the fill is at the limit price. Limit fills are not
  made worse than the requested limit.
- Stops and targets may trigger on the entry candle. Since OHLC does not reveal
  intrabar order, if both stop and target are touched, Buroka assumes the stop
  was hit first. For an entry candle, trigger checks use its high/low range;
  the open is not treated as a post-entry gap.
- On later candles, a gap through a stop exits at the worse candle open. A gap
  through a target exits at the open for price improvement. Without a gap,
  exits use the stop or target price.
- A `request_close(position_id)` signal exit executes at the next processed
  candle's open. It is an exit operation, not a market entry.

These are deterministic OHLC approximations; they do not model queue priority,
bid/ask quotes, exchange matching, or intrabar paths.

## Quantity, costs, and P&L

`quantity = lots * lot_size`. Gross P&L is `(exit - entry) * direction *
quantity * multiplier`, where direction is `+1` for buy and `-1` for sell.

All costs default to zero; Buroka does not invent fees or market frictions:

- `fee_rate` is a decimal commission/tax rate applied to each side's notional.
- `spread_bps` is the full quoted spread in basis points; half is charged on
  each side.
- `slippage_bps` is an estimated adverse cost in basis points charged on each
  side.

Spread and slippage are recorded as costs and do not change limit fill prices.
Users must set rates from their instrument, venue, and data assumptions.
Unspecified regulatory costs, financing, taxes, and short-sale constraints are
not modeled.

## End of data and result records

`finish("leave")` is the default: pending orders and open positions stay
visible in the returned snapshot and no final fills are invented.
`finish("cancel_pending")` cancels pending orders and leaves open positions.
`finish("close_at_last_close")` cancels pending orders and closes open
positions at the final processed candle close with reason `end_of_data`.

Completed `Trade` records include order and position IDs, side, entry and exit
timestamps/prices, lots, quantity, gross P&L, costs, net P&L, and exit reason.
Pending orders and open positions are returned separately in `BrokerSnapshot`.
Trade records are realized results; open positions are not marked to market.
`mark_to_market_equity(initial_capital, mark_price)` calculates liquidation-
value equity for one instrument. It adds closed-trade net P&L and open-position
unrealized P&L, subtracting entry costs already incurred and estimated exit
costs at the mark. The mark price applies to every open position in that broker
instance. It does not model cash balances, margin, financing, reserved capital,
or portfolio valuation across multiple instruments.
