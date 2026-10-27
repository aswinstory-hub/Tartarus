# Phylax Tutorials

These guides explain what each part of Phylax does, where its files live, and how to use it. Follow them in order for a first backtest, or jump to a module.

## Learning path

1. [Run your first backtest](01-first-backtest.md)
2. [Load market data](02-market-data.md)
3. [Use Buroka](03-buroka.md)
4. [Read Kijun results](04-kijun-results.md)
5. [Research with Toga](05-research-and-toga.md)
6. [Create a strategy](06-create-a-strategy.md)

## Where things live

- `Data/`: Dhan historical data and local SQLite reader.
- `Engines/buroka.py`: simulated orders and positions.
- `Engines/kijun.py`: metrics, report storage, and dashboard launcher.
- `Engines/kijun_dashboard.py`: browser results interface.
- `Engines/toga.py`: charting and indicators.
- `Strategies/sma_crossover.py`: runnable example connecting data and engines.
- `Strategies/framework.md`: structure and integrity rules for new strategies.
- `Research/`: experiments and notebooks.
- `docs/`: module reference documentation.
- `backtests/`: generated local reports (created when a strategy is run).

For a compact end-to-end guide, see the project-root [`HOWTOUSE.md`](../HOWTOUSE.md). For detailed mechanics, see [`docs/`](../docs/README.md) and the engine specifications.
