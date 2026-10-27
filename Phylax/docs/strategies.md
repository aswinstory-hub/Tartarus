# Strategies

Strategy modules live in [`Strategies/`](../Strategies/README.md). Each can be an independently runnable Python backtest. The strategy owns the hypothesis, indicators, signal timing, and sizing choice; Buroka owns simulated order state; Kijun owns reporting.

## Current example

[`Strategies/sma_crossover.py`](../Strategies/sma_crossover.py) is the runnable TATASTEEL example. It calculates fast and slow simple moving averages, submits long limit entries for upward crosses, uses stop/target brackets, and requests a signal exit on a later candle after a downward cross. Its settings are ordinary constants at the top of the file; there are no command-line options. Set `DATABASE_PATH` to use a local SQLite file; otherwise it uses Dhan historical access and needs the token configured.

## Strategy flow

1. Define and validate dates, parameters, instrument, and data source.
2. Load enough earlier candles to warm up rolling indicators.
3. Process each completed candle with Buroka.
4. Read only current and past feature values; suppress entries outside the scored date range.
5. Submit a limit order after processing the signal candle. It is eligible on the next candle.
6. Finalize Buroka using a stated end-of-data policy.
7. Pass results and, when available, periodic marked equity to Kijun, then save the report.

The reusable outline and metadata expectations are in [`Strategies/framework.md`](../Strategies/framework.md). Run the configured example with `uv run python -m Strategies.sma_crossover`. Tutorials explain how to change its settings in plain steps.
