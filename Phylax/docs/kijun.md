# Kijun Metrics and Reports

Kijun, implemented in [`Engines/kijun.py`](../Engines/kijun.py), calculates performance statistics from Buroka results and stores reports for inspection. It does not execute trades.

## Inputs and metrics

Pass a Buroka snapshot (or closed trades) to `Kijun.review`. Initial capital, run metadata, and a pandas Series of periodic marked account equity are optional inputs. Without marked equity, Kijun cannot calculate periodic Sharpe or Sortino and leaves them undefined; it does not substitute trade returns or report missing values as zero.

The report includes P&L, returns where capital is known, trade counts, win rate, average win/loss, expectancy, profit factor, drawdown and equity curves, costs, CAGR, risk ratios when valid periodic data is supplied, exposure, turnover, recovery factor, and underwater duration. Undefined values remain `None`. Floating-point metrics are rounded to three decimals in the report; counts remain integers.

When marked equity is supplied, headline equity and drawdown metrics use those marks, while closed-trade totals and separate realized curves remain available. Costs, frequency assumptions, data range, and metadata should match the actual run. Read [Engines/KIJUN.md](../Engines/KIJUN.md) for calculation details and edge cases.

## Storage and dashboard

`save` writes a latest JSON report and appends a compact record to history. Trade CSV and text summary exports are optional. Generated output is stored under `backtests/<strategy_id>/` by default and should remain local. `show_dashboard` launches the local Streamlit/Plotly report page in Tartarus's portable Chromium at `browser/chrome-win64/chrome.exe`, resolving the path relative to the repository root. It reports a clear error if that executable is missing and does not fall back to the system browser. In the SMA example, the `OPEN_DASHBOARD` setting controls whether a run opens that page; see the [SMA tutorial](../tutorial/01-first-backtest.md).

The dashboard displays saved or in-memory report data; it does not run the strategy or fetch market data. Historical stored reports are described in the engine specification.
