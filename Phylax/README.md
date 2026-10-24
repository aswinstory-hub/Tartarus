# Phylax

Phylax is a Python research workspace for historical market data, strategy
backtests, broker simulation, performance reporting, and charting. It uses
DhanHQ for on-demand historical candles and keeps all simulated execution
local. It does not place live orders.

## Project areas

- `Data/` — read-only Dhan historical candle access and a local SQLite candle
  reader. See `Data/README.md` for credentials and data formats.
- `Engines/` — Buroka simulates limit orders, Kijun reports backtest metrics,
  realized equity/drawdown curves, and an interactive browser dashboard; Toga
  creates interactive OHLC charts with SMA, EMA, and Bollinger overlays.
- `Strategies/` — independently runnable strategy backtests. The SMA crossover
  example exercises Buroka and Kijun.
- `Research/` — exploratory scripts and notebooks; Toga is intended to be
  useful here.

## Setup

Requirements: Python 3.12+ and `uv`.

```powershell
uv python install 3.12
uv sync --dev
uv run pytest
```

Put `DHAN_ACCESS_TOKEN` in the project-root `.env` file before requesting data
from Dhan, or set it in the process environment. Keep `.env` and all other
secrets, private datasets, caches, and generated reports out of source control.
The local SMA example accepts a SQLite path, so it can run without API access
when a sourced fixture is available.

## Quick links

- [HOWTOUSE.md](HOWTOUSE.md) — end-to-end examples for all three engines.
- [Strategies/framework.md](Strategies/framework.md) — recommended structure
  for new strategy backtests.
- [Engines/BUROKA.md](Engines/BUROKA.md) — order lifecycle and fill/cost
  assumptions.
- [Engines/KIJUN.md](Engines/KIJUN.md) — reported metrics and limitations.
- [Engines/TOGA.md](Engines/TOGA.md) — chart and indicator API.
- [Engines/TOGA_HOWTO.md](Engines/TOGA_HOWTO.md) — step-by-step chart guide.
- [Data/README.md](Data/README.md) — Dhan credentials, intervals, timestamps,
  and SQLite schema.

## Research integrity

Strategies process completed candles before deciding on new orders; newly
submitted limit entries are eligible starting with the next candle. Buroka is
an OHLC-based simulator with documented approximations, not an exchange matching
engine. Fees and other costs default to zero until supplied. Toga's indicators
use current and past closes only. Record the data range, parameters, costs, and
execution assumptions for every analysis. Never treat an in-sample backtest as
evidence of future performance.
