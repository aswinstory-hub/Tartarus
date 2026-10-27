# Strategies

A strategy owns its hypothesis, indicators, and entry/exit rules. It passes
completed candles to Buroka, then sends the resulting trades and equity marks
to Kijun. See [framework.md](framework.md) for the reusable backtest structure.

## SMA crossover example

[sma_crossover.py](sma_crossover.py) is a long-only golden/death cross example.
A golden cross submits a buy limit at the completed candle close; the order can
fill from the next candle onward. A death cross cancels an unfilled entry and
schedules any open long position to exit at the next candle open. Stop-loss,
take-profit, and entry expiry are simulated by Buroka.

The strategy has no command-line options. Edit its labeled constants at the top
of the file to set the date range, SMA periods, lots, stop and target, entry
TTL, initial capital, broker costs, end policy, data source, report exports,
and dashboard. The defaults are 10/30 SMAs, one lot, 2% stop, 4% target, five
eligible entry candles, 1,000,000 initial capital, and zero configured costs.
These are example settings, not recommendations.

Run the configured backtest with:

    uv run python -m Strategies.sma_crossover

Every successful run updates backtests/sma_crossover/latest.json and appends
a record to history.jsonl. With OPEN_DASHBOARD = True (the current default),
Kijun opens its local dashboard in Tartarus's portable Chromium at
browser/chrome-win64/chrome.exe, resolved relative to the repository. If the
browser files are missing, the launcher reports an error instead of using the
system browser. Set OPEN_DASHBOARD = False to skip the dashboard.
SAVE_TRADES, SAVE_TEXT, or SAVE_REPORT enable optional exports.
DATABASE_PATH selects a local SQLite database; leave it as None to request
Dhan historical candles using DHAN_ACCESS_TOKEN.

The strategy fetches three times the slow SMA period in calendar days before
the requested start date for warm-up, but it does not submit orders before
START_DATE. Data validation, broker accounting, and report preparation live
in their respective modules. The TATA STEEL fixture database is not currently
included. See [Buroka assumptions](../Engines/BUROKA.md) before interpreting
OHLC-based fills and costs.
