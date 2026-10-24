# Kijun — Metrics, Curves, and Results Dashboard

Kijun reviews Buroka's closed trades, calculates performance metrics, stores
machine-readable reports, and opens a local browser dashboard built with
Streamlit and Plotly. The results page has interactive equity and drawdown
charts, a trade P&L chart, KPI cards, and downloadable trade and metrics tables.
It is a local report viewer; it does not connect to a broker or place orders.

## Review results

Pass the whole Buroka snapshot to `review`, or pass a sequence of trades to
`analyze`:

```python
from Engines import Kijun

kijun = Kijun()
report = kijun.review(
    snapshot,
    initial_capital=100_000,  # leave out when the actual value is unknown
    periodic_equity=daily_marked_equity,  # pandas Series: timestamp -> marked account equity
    periods_per_year=252,
    risk_free_rate=0.0,  # annual rate as a decimal
    metadata={
        "strategy": "example",
        "instrument": "TATASTEEL",
        "timeframe": "1d",
        "data_source": "Dhan historical data",
        "data_range": {
            "start_inclusive": "2025-01-01",
            "end_exclusive": "2025-06-01",
        },
    },
)
kijun.print_summary(report)
kijun.show_dashboard(report)
```

Call `show_dashboard` after the report is ready. It starts a local Streamlit
server and opens the results in the default browser. The SMA crossover example
does this automatically after every backtest. To open an existing saved report
manually in PowerShell:

```powershell
$env:PHYLAX_KIJUN_REPORT = "backtestMetricsLog/example-run.json"
uv run streamlit run Engines/kijun_dashboard.py
```

## Metrics

Kijun reports net P&L and return, total trade count, win rate, average win and
loss, expectancy, profit factor, trading costs and their fee/spread/slippage
components, realized equity and drawdown curves, maximum drawdown, CAGR,
Sharpe, Sortino, Calmar, exposure, price-notional turnover, recovery factor,
and time underwater. Additional trade counts, streaks, holding time, and
long/short summaries are available in the metrics report and dashboard.

Profit factor and payoff ratio remain undefined when there are no losing
trades. Percentage return metrics require positive initial capital. CAGR
requires a positive test-window duration and positive ending capital. Sharpe
and Sortino require a caller-supplied `pandas.Series` of periodic marked
account equity indexed by observation time; the caller also supplies
`periods_per_year` and the annual `risk_free_rate` (decimal). They are left
undefined when too few observations or no required variation/downside exists.
Trade-exit realized equity is not substituted for periodic mark-to-market
equity.

Total costs are the actual aggregate reported by Buroka. When run metadata
contains `costs_and_fill_assumptions` (`fee_rate`, `spread_bps`,
`slippage_bps`) and `broker_settings.pnl_multiplier`, Kijun also calculates
fee, spread, and slippage amounts from executed entry/exit notionals. These
components remain undefined when the inputs are missing. The strategy must
record the same settings used to construct Buroka.

## Curves and assumptions

`report.curves["equity_curve"]` contains a starting point and one point per
closed trade exit. When initial capital is supplied it is account equity;
without it, the values are cumulative realized P&L starting at zero.
`report.curves["drawdown_curve"]` contains amount and percentage from the
previous realized-equity peak. Percentages are omitted without initial
capital. These are realized event curves, not candle-by-candle mark-to-market;
open positions are excluded. The dashboard labels this distinction. The browser
charts support hover details and range selection.

Exposure is the union of closed-trade holding intervals divided by the
metadata data range (`start_inclusive`, `end_exclusive`) when provided. Without
that range, it uses the span from the first entry to the last exit. Open
positions, unrealized P&L, and overlap-adjusted leverage are not inferred.
Drawdown follows exit-time order. Trades with missing/invalid exit timestamps
still contribute to trade totals when their P&L is usable, but cannot appear
in the dated curves or streak calculations.

## Save reports

```python
json_path, metrics_csv, summary_txt = kijun.save(
    report,
    output_dir="backtestMetricsLog",
    stem="example-run",
)
```

Kijun writes JSON (including curves and run metadata), a metrics CSV, a text
summary, and separate `<stem>-equity.csv` and `<stem>-drawdown.csv` files. The
periodic equity input, when supplied, is also written to
`<stem>-periodic-equity.csv`. The
method continues to return the original three paths for compatibility. The
output folder is ignored by Git by default. Undefined metrics remain `None`; Kijun does not infer capital,
fees, multipliers, benchmark returns, fills, or missing trade data.
