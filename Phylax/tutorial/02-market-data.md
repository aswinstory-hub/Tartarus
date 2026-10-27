# Tutorial 2: Load Market Data

The `Data` package is in `Data/`. It supports on-demand historical candles from Dhan and read-only candles from a local SQLite file. It does not place orders.

## Dhan historical candles

Set `DHAN_ACCESS_TOKEN` in the project-root `.env` file, then use the public package exports:

```python
from datetime import date

from Data import DhanClient, Instrument

tata_steel = Instrument(
    security_id="3499",
    exchange_segment="NSE_EQ",
    instrument="EQUITY",
    symbol="TATASTEEL",
)
candles = DhanClient().fetch(
    tata_steel, date(2025, 1, 1), date(2025, 4, 1), interval="1d"
)
frame = candles.frame
print(frame.tail())
print("gaps:", candles.gaps)
print("duplicates:", candles.duplicate_timestamps)
```

The output has Date, Time, Open, High, Low, Close, and Volume if the source provides volume. Its timezone-aware index is used for chronological calculations. The end date is exclusive. Verify the example security ID using Dhan's current instrument list before using it for important work.

## Local SQLite candles

```python
from Data import Instrument, SQLiteCandleStore

store = SQLiteCandleStore("Data/test_data/tata_steel.db")
candles = store.fetch(
    Instrument("3499", "NSE_EQ", "EQUITY", "TATASTEEL"),
    start,
    end,
    interval="1d",
)
```

The SQLite schema and filtering rules are documented in [`Data/README.md`](../Data/README.md). A valid database must already exist; Phylax does not fabricate missing candles. Set `DATABASE_PATH` at the top of the SMA strategy to use the database.

For full validation and error behavior, see [Market data module](../docs/data-module.md).
