# Tutorial 1: Run Your First Backtest

This walkthrough runs the existing SMA crossover strategy. It fetches historical candles from Dhan unless you give it a local SQLite database.

## 1. Prepare the project

Open PowerShell in the Phylax project folder and install dependencies:

```powershell
uv sync --dev
```

To use Dhan, put your token in the project-root `.env` file:

```dotenv
DHAN_ACCESS_TOKEN=your_token_here
```

The `.env` file must stay private. Alternatively, set `DATABASE_PATH` near the top of the strategy file to a local SQLite file. The repository currently does not include a TATASTEEL fixture database.

## 2. Run the strategy

```powershell
uv run python -m Strategies.sma_crossover
```

To change the run, edit the labeled constants near the top of `Strategies/sma_crossover.py`: `START_DATE` and `END_DATE` define an inclusive start and exclusive end; other settings control SMA periods, sizing, costs, exports, and the dashboard. The current defaults are fast SMA 10, slow SMA 30, one lot, 2% stop, 4% target, initial capital 1,000,000, and zero configured fees/spread/slippage. These are code defaults, not recommendations or claims about actual costs.

The run prints a summary and stores the latest report and a history record under `backtests/sma_crossover/`. With `OPEN_DASHBOARD = True` (the current default), Kijun starts its local Streamlit results page and opens it in Tartarus's portable Chromium at `browser/chrome-win64/chrome.exe`. The browser path is resolved relative to the Tartarus repository, so the project can move to another drive. If Chromium is missing, the launcher reports its expected path and does not open the system default browser. Set `OPEN_DASHBOARD = False` to run without opening the dashboard. `SAVE_TRADES`, `SAVE_TEXT`, and `SAVE_REPORT` control extra exports.

## 3. Understand the signal and fill timing

The strategy compares a fast and slow moving average. An upward crossover can submit a buy limit at the completed candle close. Because Buroka has already processed that candle, the new limit order first becomes eligible on the next candle. A downward crossover requests an exit for a later candle. See [Create a strategy](06-create-a-strategy.md) for the full loop.

## 4. Read the result honestly

Kijun distinguishes closed-trade P&L from marked account equity. Return and risk metrics depend on valid capital and equity observations; undefined metrics can be shown as missing. Costs default to zero in this example unless configured, so results do not represent all-in real trading costs. Buroka's OHLC fill assumptions are approximations. See [Kijun results](04-kijun-results.md) and the [Buroka reference](../docs/buroka.md).
