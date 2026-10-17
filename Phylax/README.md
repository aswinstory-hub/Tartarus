# Quant Research Sandbox

Git-portable, Python-first workspace for quantitative research and strategy backtesting.

## Four main folders
- `Data/`: Python access to Dhan market data on demand.
- `Engines/`: specifications for Buroka (broker simulator), Kijun (metrics), and Toga (charts).
- `Strategies/`: independently runnable strategy/backtest Python files.
- `Research/`: manually written Python scripts and Jupyter notebooks.

**Documentation-first scaffold. The engines are not implemented.**

## Setup
Install `uv`, then run:
```powershell
uv python install 3.12
uv sync --dev
uv run pytest
```
Commit `pyproject.toml` and `uv.lock`. Do not commit secrets, datasets, or generated outputs.

## Principles
Python only; no C++. Prefer a self-contained backtest per strategy. Extract shared code only when it improves correctness or meaningfully reduces duplication. Avoid an overbuilt universal framework. Prevent look-ahead bias and keep local simulation separate from live Dhan execution.
