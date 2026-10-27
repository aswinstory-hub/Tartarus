# Market Data Module

The `Data/` package provides read-only historical candle access. The public exports are in [`Data/__init__.py`](../Data/__init__.py), and the implementation is in [`Data/dhan.py`](../Data/dhan.py).

## Data sources

- `DhanClient` requests historical DhanHQ v2 candles on demand.
- `SQLiteCandleStore` reads existing candle rows from a local SQLite database.
- `fetch_candles` lets callers use either source behind the same fetch interface.

Neither source places trades. Dhan access requires a valid `DHAN_ACCESS_TOKEN` in the project `.env` or process environment. An explicit token passed when constructing `DhanClient` takes precedence. Keep credentials out of source files and version control. See [`Data/README.md`](../Data/README.md) for current intervals, date handling, schema, and API limits implemented by the module.

## Returned data

The fetch result is `CandleData`. Use `result.frame` for its pandas DataFrame. The columns are `Date`, `Time`, `Open`, `High`, `Low`, `Close`, plus `Volume` when the source includes it. A timezone-aware timestamp index is retained for chronological processing. The result also makes detected duplicate timestamps and applicable intraday gaps visible; the module does not interpolate missing candles.

Example:

```python
from datetime import date

from Data import DhanClient, Instrument

instrument = Instrument(
    security_id="3499",
    exchange_segment="NSE_EQ",
    instrument="EQUITY",
    symbol="TATASTEEL",
)
result = DhanClient().fetch(
    instrument, date(2025, 1, 1), date(2025, 4, 1), interval="1d"
)
frame = result.frame
print(frame[["Date", "Time", "Open", "High", "Low", "Close"]].tail())
```

The security ID above is the example mapping currently shown by the project; refresh it against Dhan's instrument list before relying on it. The end date is exclusive. For offline use, pass a database path to `SQLiteCandleStore` and make sure its schema and candles match the requested symbol and interval. A TATA STEEL fixture database is not currently included.

## Validation and limits

Date ranges, OHLC values, and source payloads are validated. Dhan, network, malformed-response, and local database errors are raised rather than silently replaced with fabricated prices. Token renewal, live quotes, symbol resolution, and exchange-session bar synthesis are outside this module's scope.
