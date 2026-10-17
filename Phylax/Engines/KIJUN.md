# Kijun — Metrics and Reporting Engine

Receives Buroka results through the strategy file, calculates metrics, prints a summary and persists a report.

The plan names `backtestMetricsLog/` or `Notenbuch/`. Choose one canonical folder at implementation; default recommendation: `backtestMetricsLog/`.

Possible metrics: return, maximum drawdown, win rate, average win/loss, expectancy, trade count, exposure, turnover, costs and benchmark comparison. Sharpe/Sortino require explicit assumptions and sufficient observations.

Handle no-trade runs, undefined metrics, zero denominators, NaN/inf and missing fields. Record strategy/parameters, data source/range, instrument/timeframe, costs/fill assumptions, run timestamp and code revision when available. Prefer JSON/CSV plus a readable summary. Generated logs should be Git-ignored by default.
