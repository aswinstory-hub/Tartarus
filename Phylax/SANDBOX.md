# SANDBOX.md — Operating Contract

## 1. Mission
Research quantitative trading ideas, test strategies, inspect market behavior and iterate quickly. Optimize for reproducibility, realistic assumptions and evidence, not for building the largest possible framework.

## 2. Fixed stack
- Python 3.12+
- `uv` for Python version, environment and dependency management
- NumPy and pandas for numerical work
- pytest for tests; Ruff for linting/formatting
- Jupyter notebooks for exploratory work
- Python only; C++ is out of scope

Add dependencies only for concrete needs. Keep `pyproject.toml` and `uv.lock` in Git. Keep environments, credentials, datasets and generated outputs out of Git.

## 3. Top-level structure

### `Data/`
Planned Python module to retrieve Dhan market data on demand for both `Strategies/` and `Research/`. Before implementation, verify current official DhanHQ documentation for authentication, endpoints, instrument identifiers, intervals, limits, rate limits and response schemas. Normalize responses into documented timestamp-aware data structures. Make errors, gaps and duplicate bars visible. Keep credentials in environment variables or a supported secret store. Data access must not place orders.

### `Engines/`
Three planned engines, documented in separate files:
1. **Buroka** — simulated broker and order lifecycle.
2. **Kijun** — performance metrics and reporting.
3. **Toga** — charts and optional indicators.

This scaffold documents the engines; it does not implement them unless the user explicitly asks.

### `Strategies/`
Independently runnable strategy/backtest Python files. A file may define parameters, obtain data through `Data/`, run its loop, interact with Buroka and pass results to Kijun. Start with one self-contained file per strategy. Extract shared utilities only if they materially improve correctness or reduce duplication.

### `Research/`
Manual Python scripts and Jupyter notebooks for exploration, hypothesis formation, features/indicators, plots, statistical checks and early experiments. Toga will be used most often here.

## 4. Buroka — broker simulation specification
Buroka simulates orders and positions during historical backtests. It is not a live broker.

### Planned loop
1. Strategy gets the current candle from historical data.
2. Strategy passes the candle to Buroka so pending orders and open positions can be updated.
3. Strategy evaluates only information available at that time.
4. If conditions meet, strategy submits a limit-entry order.
5. Each next iteration passes its candle to Buroka for order/position processing.
6. Buroka returns documented trade/result data.
7. Strategy passes completed results to Kijun.

The exact order of candle processing and new order submission must be specified and tested to prevent same-candle look-ahead.

### Order shape
```python
{
    "side": "buy",  # or "sell"
    "entry_price": 100.0,
    "sl": 98.0,
    "tp": 104.0,
    "lots": 1
}
```
Illustrative schema, not implemented code. Market entries are not supported. Define validation, price relationships, lot-size conversion, instrument multiplier, pending-order expiry/cancellation, duplicates, position limits and invalid-order behavior before implementation.

### Execution assumptions to settle before coding
- Limit fill conditions and gap-through behavior.
- Fees, taxes, spread and slippage.
- Whether SL/TP may trigger on entry candle.
- If SL and TP both fall inside one OHLC candle, how ambiguity is resolved.
- Gaps through stops, end-of-data pending orders and open positions.
- Lot conversion, shorting, leverage and margin.

OHLC candles do not reveal the true intrabar path. Use documented, conservative assumptions and tests.

### Output
Return a stable, documented structure rather than an arbitrary mix of dicts and lists. Completed trades should include side, entry/exit times and prices, quantity, gross/net P&L, costs, exit reason and order identifiers where relevant. Pending orders and open positions should be explicit state if needed.

## 5. Kijun — metrics/reporting specification
Kijun receives Buroka results through the strategy file, calculates metrics, prints a summary and stores a report.

The plan names `backtestMetricsLog/` or `Notenbuch/`. Choose one canonical folder at implementation time; default recommendation is `backtestMetricsLog/`.

Possible metrics: total/annualized return, maximum drawdown, win rate, average win/loss, expectancy, trade count, exposure, turnover, cost impact and benchmark comparison. Sharpe/Sortino require explicit assumptions and enough observations.

Handle no-trade runs, undefined metrics, zero denominators, NaN/inf and missing fields explicitly. Do not report undefined metrics as zero without labeling them. Store strategy/parameters, data source/range, instrument/timeframe, costs/fill assumptions, run timestamp and code revision when available. Prefer machine-readable JSON/CSV plus a human-readable summary. Ignore generated logs in Git by default.

## 6. Toga — chart/indicator specification
Toga accepts OHLC data and renders a chart, optionally with indicators. It is mainly for Research. It may be used in strategy analysis but must not handle broker simulation or performance accounting.

Validate OHLC columns, timestamp order, timezone and missing data. Select a plotting library when implementation is requested. Label symbol, timeframe, range and indicator parameters where available. Indicator calculations must not introduce future-data leakage; make gaps visible instead of fabricating data.

## 7. Strategy-file expectations
Make these easy to locate:
1. Hypothesis and rationale.
2. Instrument, timeframe and data source.
3. Parameters/configuration.
4. Data retrieval through `Data/`.
5. Signal/feature calculations.
6. Backtest loop and order decisions.
7. Buroka interaction and result collection.
8. Kijun reporting.
9. Tests/validation and known limitations.

Self-contained strategy files are acceptable. Do not extract shared code without a real benefit.

## 8. Research workflow
Use `Research/` for scripts and notebooks. Record data source, instrument, date range, assumptions, parameters and dependencies. A research hypothesis can become a strategy once it has clear rules, reproducible inputs and a testable evaluation.

## 9. Backtest integrity
Disclose instrument, timeframe, timezone, data source/date range, signal and earliest fill times, limit-fill assumptions, costs/spread/slippage, position sizing, lot conversion, leverage/margin, risk limits, missing-data handling and validation method.

Avoid look-ahead bias, survivorship bias, leakage and train/test contamination. Use chronological splits for time series and walk-forward validation when useful. One optimized in-sample result does not prove a durable edge.

## 10. Dhan/live boundary
Dhan is the intended market-data source and future live execution platform, but Buroka is only a local simulator.
- Dhan data access belongs in `Data/`.
- Keep live execution separate from Buroka.
- Never place live orders from a backtest or research run.
- Verify current official Dhan documentation, Cloud runtime, dependencies, secret handling, API permissions, network/IP requirements and pricing before deployment.
- Live mode must be disabled by default and require explicit authorization.
- Test rejections, timeouts, duplicate prevention, reconciliation, disconnect recovery and kill-switch behavior before live use.

## 11. Codex workflow
1. Read this file and the relevant engine specification.
2. Inspect existing files and tests.
3. Identify the concrete research goal and assumptions.
4. Make the smallest useful change.
5. Add tests for critical logic and edge cases.
6. Run checks and report actual results only.
7. Summarize files changed, assumptions, limitations and next research step.

Do not implement engines during documentation-only tasks or invent data, API behavior, tests or performance claims.

## 12. Definition of done
Documentation is done when another agent can implement without guessing critical behavior. Code is done when tested, documented and reproducible. Promising backtests proceed to robustness checks and paper trading, not automatic live deployment.
