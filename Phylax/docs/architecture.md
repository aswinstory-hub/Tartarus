# Architecture Overview

```text
Data/ ── candles ──> Engines/DataQuality ── clean candles ──> Strategies/
      └─────────────────────────────────────────────────────> Research/
Strategies/ ── candles/orders ─────> Engines/Buroka
Strategies/ <──── trade results ─── Engines/Buroka
Strategies/ ── completed results ──> Engines/Kijun
Research/ ── OHLC + indicators ────> Engines/Toga
```

Data retrieves Dhan market data. DataQuality normalizes candles and makes safe
repairs before a strategy uses them; ambiguous price errors stop the run.
Buroka is a local simulator, Kijun computes and logs metrics, Toga charts OHLC
data, Strategies contains independent Python backtests, and Research contains
exploratory scripts/notebooks. Python only; no C++.
