# Codex Instructions

Before editing, read `SANDBOX.md` and the relevant specification under `Engines/`.

1. The four project areas are `Data/`, `Engines/`, `Strategies/`, and `Research/`.
2. Python only. Do not introduce C++.
3. This initial task is documentation/specification only. Do not implement Buroka, Kijun, Toga, Dhan data access, or strategies unless explicitly asked.
4. A strategy may be a self-contained, independently runnable Python backtest file.
5. The strategy loop passes each current candle to Buroka, submits a limit-entry-only order when conditions meet, collects Buroka results, then passes results to Kijun.
6. Order fields: `side` (`buy`/`sell`), `entry_price`, `sl`, `tp`, `lots`. Document validation and lifecycle behavior before implementation.
7. Toga accepts OHLC data and can optionally add indicators; it is mainly for Research.
8. Extract shared utilities only when they improve correctness or reduce meaningful duplication.
9. Never invent market data, API behavior, fees, fills, or test results. Verify current official Dhan documentation before API implementation.
10. Prevent look-ahead bias and make candle availability/fill timing explicit.
11. Document fees, spread, slippage, limit fills, SL/TP collision rules and end-of-data handling.
12. Keep live order execution separate from Buroka. Never place real orders without explicit authorization.
13. Never hardcode, print, or commit credentials. Do not commit datasets, private data, caches, or generated reports by default.
14. Add tests for meaningful behavior and report only tests actually run.

Finish implementation tasks by summarizing changed files, actual tests, assumptions, limitations and risks.
