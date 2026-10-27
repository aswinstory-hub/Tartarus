# Data

Read-only historical market data access for `Strategies/` and `Research/`.
`Data.dhan.DhanClient` fetches DhanHQ v2 daily and intraday candles on demand;
`SQLiteCandleStore` reads the same normalized candles from a local SQLite file.
Neither client can place or manage orders.

## Dhan setup

Put `DHAN_ACCESS_TOKEN` in the project-root `.env` file or set it in the process
environment. `DhanClient` loads `.env` without overriding a token already set in
the process; an explicit `access_token` argument takes precedence over both.
The `.env` file is ignored by Git. Never commit or share it, and do not put
tokens in source files, notebooks, command history, or the database. Dhan
access tokens generated from Dhan Web are documented as valid for 24 hours.
Data API access may require an active Data API subscription.

```dotenv
DHAN_ACCESS_TOKEN=put_your_token_here
```

Replace the placeholder locally; do not put a real token in `.env.example`.

```python
from datetime import date

from Data import DhanClient, Instrument

tata_steel = Instrument(
    security_id="3499", exchange_segment="NSE_EQ", instrument="EQUITY",
    symbol="TATASTEEL",
)
candles = DhanClient().fetch(
    tata_steel, date(2024, 8, 1), date(2024, 8, 6), interval="1d"
)
print(candles.frame)
print(candles.gaps, candles.duplicate_timestamps)
```

The security identifier is an example mapping; refresh it against Dhan's current
instrument list before relying on it. Supported intervals are daily (`1d`) and
intraday minutes (`1`, `5`, `15`, `25`, `60`). Intraday requests are split into
windows of at most 90 days. The requested end is exclusive. Date-only ranges
and naive datetimes are interpreted in `Asia/Kolkata`.

## Normalized result

`CandleData.frame` has columns `Date`, `Time`, `Open`, `High`, `Low`, `Close`,
and optional `Volume`. Date and time columns are display-friendly local IST
values; the timezone-aware timestamp index is retained for sorting, strategy
timing, and duplicate/gap detection. Rows are timestamp-sorted. Duplicate rows
are retained and their timestamps are exposed in `duplicate_timestamps`.
`gaps` lists intraday timestamp gaps on the same weekday and local date; it
does not infer missing bars across overnight or session boundaries. No values
are interpolated. If volume is absent in a source response or SQLite schema,
the `Volume` column is omitted.

Rows with negative volume are excluded rather than changed, and their timestamps
are exposed in `invalid_volume_timestamps`. The SMA strategy prints a warning
and includes these timestamps in the saved report metadata so a run that omits
a source anomaly remains auditable.

## Local SQLite file

`SQLiteCandleStore(path)` expects a read-only database with this schema:

```sql
CREATE TABLE candles (
    symbol TEXT, interval TEXT, timestamp TEXT,
    open REAL, high REAL, low REAL, close REAL, volume INTEGER
);
```

Timestamps may be ISO-8601 (prefer an explicit offset) or epoch seconds.
The `volume` column is optional; symbol, interval, timestamp, open, high, low,
and close are required.
`fetch_candles(..., source=SQLiteCandleStore(path))` uses the same normalized
result as Dhan.

The requested TATA STEEL test database is not included yet: no real source
candles or Dhan credentials were present when this module was built, and test
market data must not be fabricated. The reader is ready for a sourced database
to be added at `Data/test_data/tata_steel.db`.

## Scope and limits

- This module makes historical candle requests only; it does not fetch live
  quotes, renew tokens, resolve symbols, or access trading endpoints.
- It does not silently retry. Dhan errors, network failures, malformed arrays,
  invalid OHLC values, and local database errors are raised as exceptions.
- Exchange holidays and expected session bars are not synthesized. A gap means
  a missing interval between returned same-day intraday timestamps, not proof
  that Dhan omitted a candle.
- Dhan's historical API uses Unix timestamps and has endpoint-specific fields;
  consult current official documentation before changing request behavior.
