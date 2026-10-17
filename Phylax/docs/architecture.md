# Architecture Overview

```text
Data/ ──────────────┬──────────────> Strategies/
                    └──────────────> Research/
Strategies/ ── candles/orders ─────> Engines/Buroka
Strategies/ <──── trade results ─── Engines/Buroka
Strategies/ ── completed results ──> Engines/Kijun
Research/ ── OHLC + indicators ────> Engines/Toga
```

Data retrieves Dhan market data. Buroka is a local simulator, Kijun computes/logs metrics, Toga charts OHLC data, Strategies contains independent Python backtests, and Research contains exploratory scripts/notebooks. Python only; no C++.
