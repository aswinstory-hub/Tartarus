# Toga — Chart and Indicator Engine

Accept OHLC data and render a chart, optionally with indicators. Primarily used in `Research/`.

Validate required columns, timestamp order, timezone and missing data. Choose a plotting library when implementation is requested. Keep visualization separate from broker simulation and metrics. Label symbol, timeframe, date range and indicator parameters where available. Prevent future-data leakage and make gaps visible.
