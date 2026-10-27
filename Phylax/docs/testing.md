# Tests and Project Checks

Phylax uses pytest for automated tests and Ruff for linting, configured in [`pyproject.toml`](../pyproject.toml). Test files are under [`tests/`](../tests/).

From the project root, install project and development dependencies and run the checks:

```powershell
uv sync --dev
uv run pytest
uv run ruff check .
```

Tests should verify behavior and assumptions rather than claim that a backtest is profitable. Useful areas include candle normalization, order lifecycle and timing, collision and end-of-data rules, metric behavior for empty or incomplete data, and strategy signal/warm-up logic. Never state that a test passed unless it was actually run.
