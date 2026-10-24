# Strategies

Start with one independently runnable Python file per strategy. A strategy may
fetch data through `Data/`, run its loop, interact with Buroka, and pass
completed results to Kijun for metrics and reports.

See [framework.md](framework.md) for the recommended file structure, warm-up
handling, Buroka lifecycle, and Kijun reporting pattern.

## SMA crossover example

`sma_crossover.py` is a long-only golden/death cross example and an integration
exercise for Buroka. It submits a buy limit at the completed signal candle's
close, uses a configurable stop and target bracket, and requests a signal exit
at the next candle open after a death cross. Defaults are 10/30 SMAs, one lot,
2% stop, 4% target, and five eligible candles for an unfilled entry. These are
example parameters, not claims of profitability. The command line exposes lot
size, multiplier, stop/target, entry expiry, end-of-data policy, fee, spread,
slippage, and initial-capital settings. Initial capital affects Kijun return
metrics only; it does not change position sizing. Costs default to zero until
configured; pass sourced assumptions for meaningful net P&L. Starting capital
defaults to 1,000,000 and can be overridden with `--initial-capital`. Kijun's
dashboard opens automatically after the report is saved.

The CLI fetches three times the slow SMA period in calendar days before the
scored start date, warms indicators without submitting pre-start orders, and
then evaluates signals inside the requested date range. It warns when fewer
than one full slow-SMA period of warm-up candles are present.

Run against Dhan data (set `DHAN_ACCESS_TOKEN` first):

```powershell
uv run python -m Strategies.sma_crossover --start 2024-01-01 --end 2024-06-01
```

Or use a local SQLite file with the schema documented in `Data/README.md`:

```powershell
uv run python -m Strategies.sma_crossover --start 2024-01-01 --end 2024-06-01 --db Data/test_data/tata_steel.db
```

The TATA STEEL database is not included until sourced candles are available.
No strategy test data is fabricated. See `Engines/BUROKA.md` for explicit
candle timing, fill, cost, and end-of-data assumptions.
