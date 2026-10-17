# Strategies

Start with one independently runnable Python file per strategy. It may define parameters, retrieve data through `Data/`, run the backtest loop, interact with Buroka, and pass results to Kijun. Document hypothesis, instruments/timeframe, data, costs/fill assumptions, validation and failure modes. Extract shared code only when it materially improves correctness or reduces duplication.
