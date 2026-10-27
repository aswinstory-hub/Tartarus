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
latest_path = kijun.save(report, strategy_id="example")
kijun.show_dashboard(report, report_path=latest_path)  # opens Tartarus portable Chromium
```

Call `show_dashboard` after the report is ready to start a local Streamlit
server and open the results in Tartarus's portable Chromium at
`../browser/chrome-win64/chrome.exe` (resolved relative to the Tartarus repo).
The dashboard does not fall back to the system browser if Chromium is missing.
The SMA example does this only when `OPEN_DASHBOARD` is enabled in its settings.
Saved `latest.json` files include a selector for historical runs. To open the
latest saved result manually in PowerShell:

```powershell
$env:PHYLAX_KIJUN_REPORT = "backtests/example_strategy/latest.json"
uv run streamlit run Engines/kijun_dashboard.py
```

## Metrics

Kijun reports net P&L and return, total trade count, win rate, average win and
loss, expectancy, profit factor, trading costs and their fee/spread/slippage
components, realized equity and drawdown curves, maximum drawdown, CAGR,
Sharpe, Sortino, Calmar, exposure, price-notional turnover, recovery factor,
and time underwater. Additional trade counts, streaks, holding time, and
long/short summaries are available in the metrics report and dashboard.
Floating-point metric values in reports and dashboard tables are rounded to
three decimal places; integer counts remain whole numbers. Calculations use
full precision before the final report values are rounded.

When periodic marked equity is supplied, `net_pnl`, ending capital, return,
equity curve, drawdown, CAGR, Calmar, Sharpe, and Sortino use that series.
`total_net_pnl` remains realized P&L from closed trades. The report also keeps
`realized_equity_curve` and `realized_drawdown_curve` for comparison.

Profit factor and payoff ratio remain undefined when there are no losing
trades. Percentage return metrics require positive initial capital. CAGR
requires a positive test-window duration and positive ending capital. Sharpe
and Sortino require a caller-supplied `pandas.Series` of periodic marked
account equity indexed by observation time; the caller also supplies
`periods_per_year` and the annual `risk_free_rate` (decimal). They are left
undefined when too few observations or no required variation/downside exists.
They also remain undefined if marked equity reaches zero or below, where
percentage returns cease to be meaningful.
When no marked series is supplied, ratios stay undefined; Kijun does not
substitute trade-exit returns or show missing values as zero.

Total costs are the actual aggregate reported by Buroka. When run metadata
contains `costs_and_fill_assumptions` (`fee_rate`, `spread_bps`,
`slippage_bps`) and `broker_settings.pnl_multiplier`, Kijun also calculates
fee, spread, and slippage amounts from executed entry/exit notionals. These
components remain undefined when the inputs are missing. The strategy must
record the same settings used to construct Buroka.

## Curves and assumptions

Without periodic marks, `report.curves["equity_curve"]` contains a starting
point and one point per closed trade exit. When initial capital is supplied it
is realized account equity; without it, values are cumulative realized P&L
starting at zero. Its drawdown is measured from realized-equity peaks and its
percentages require initial capital. With periodic marks, `equity_curve` and
`drawdown_curve` use candle-close
liquidation-value equity. The realized curves remain available separately for
comparison. Dashboard titles identify the selected basis.

Exposure is the union of closed-trade holding intervals divided by the
metadata data range (`start_inclusive`, `end_exclusive`) when provided. Without
that range, it uses the span from the first entry to the last exit. Open
positions, unrealized P&L, and overlap-adjusted leverage are not included in
exposure. Marked drawdown follows candle-close order; realized drawdown follows
exit-time order. Trades with missing/invalid exit timestamps
still contribute to trade totals when their P&L is usable, but cannot appear
in the dated curves or streak calculations.

## Save reports

```python
latest_path = kijun.save(
    report,
    output_root="backtests",
    strategy_id="example_strategy",
    save_trades=False,
    save_text=False,
)
```

Each strategy gets `latest.json` with the full data needed by the dashboard and
`history.jsonl` with one compact metadata-and-metrics record per run. `save`
returns the latest report path and appends history without replacing earlier
records. Detailed trade CSV files under `trades/` and readable summaries under
`summaries/` are created only when requested. `write_text_summary(report, path)`
can also generate a TXT summary from an existing report. Old standalone JSON
reports remain readable by the dashboard; they are not migrated or deleted.
The `backtests/` folder is ignored by Git. Undefined metrics remain `None`;
Kijun does not infer capital, fees, multipliers, benchmark returns, fills, or
missing trade data.
