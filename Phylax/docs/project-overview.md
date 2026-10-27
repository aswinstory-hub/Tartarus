# Phylax Project Overview

Phylax is a Python workspace for researching historical market data and testing strategies. Historical data flows into a strategy; Buroka simulates that strategy's orders; Kijun summarizes the result; and Toga can chart candles and indicators for research. These modules do not place live orders.

## Main folders

| Folder | Responsibility | Start here |
| --- | --- | --- |
| [`Data/`](../Data/README.md) | Fetch historical candles from Dhan or read candles from SQLite | `Data/dhan.py` |
| [`Engines/`](../Engines/README.md) | Simulated broker, performance analysis, and charting | `Engines/buroka.py`, `Engines/kijun.py`, `Engines/toga.py` |
| [`Strategies/`](../Strategies/README.md) | Runnable strategy backtests | `Strategies/sma_crossover.py` |
| [`Research/`](../Research/README.md) | Manual experiments and notebooks | Add research scripts and notebooks here |
| [`docs/`](README.md) | Module reference pages | This directory |
| [`tutorial/`](../tutorial/README.md) | Beginner-oriented walkthroughs | Start with tutorial 1 |

## Typical data flow

1. `Data` returns normalized OHLC candles in a `CandleData` object. Its `frame` is a pandas DataFrame and has a timezone-aware timestamp index.
2. A strategy calculates features using only candles available up to the current decision point.
3. The strategy passes each completed candle to Buroka, then decides whether to submit an entry. An order submitted after processing a candle first becomes eligible on the next candle.
4. Buroka returns completed trades plus any still-open positions and pending orders.
5. The strategy passes those results and optional marked account equity to Kijun.
6. Kijun calculates metrics and stores a report. Its optional Streamlit dashboard opens in Tartarus's portable Chromium (`browser/chrome-win64/chrome.exe`), resolved relative to the repository.
7. Toga can render an interactive candle chart and trailing indicators for research.

## Boundaries

- Dhan access in `Data/` is for historical market data. It is not an order interface.
- Buroka is an OHLC-based simulation, not an exchange matching engine.
- Kijun reports the data given to it; missing capital, costs, or marked equity are not guessed.
- Toga visualizes data and indicators. It does not make strategy or accounting decisions.
- Generated reports belong under `backtests/`; market data and credentials must be handled as private local inputs.

See [SANDBOX.md](../SANDBOX.md) for the workspace operating contract and [HOWTOUSE.md](../HOWTOUSE.md) for combined examples.
