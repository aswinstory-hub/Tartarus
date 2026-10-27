# Toga Charts and Indicators

Toga is the research visualization engine in [`Engines/toga.py`](../Engines/toga.py). It converts validated OHLC candles into an interactive HTML chart and optionally calculates trailing indicators. It does not simulate orders or calculate performance metrics.

## Inputs and outputs

`Toga.plot` accepts a `CandleData` result or pandas DataFrame. It expects numeric, internally consistent OHLC values and an ordered, unique, timezone-aware timestamp index; separate Date and Time columns can be used to construct timestamps. Volume is optional. Toga raises a data error for invalid candles rather than sorting, deduplicating, or inventing values.

Use `IndicatorSpec("sma", period)`, `IndicatorSpec("ema", period)`, or `IndicatorSpec("bollinger", period, deviations=...)` to request chart overlays. SMA and Bollinger calculations use trailing windows; EMA uses closes available up through each row. Results remain empty until their warm-up period is available. `calculate_indicator` returns values for use in Python without rendering.

The returned chart can be saved as a self-contained HTML file with `save_html` or opened with `open`; `plot(..., show=True)` opens a temporary chart immediately. The web page provides candle hover details, zoom/pan, optional volume, and browser-side indicator controls. See [Engines/TOGA.md](../Engines/TOGA.md) and [Engines/TOGA_HOWTO.md](../Engines/TOGA_HOWTO.md) for full details.
