# Toga — Interactive Chart and Indicator Engine

Toga creates a self-contained interactive HTML chart for research. It accepts
OHLC data, optionally shows volume, and can overlay trailing SMA, EMA, and
Bollinger Bands. It does not trade or calculate backtest results.

## Input rules

- Required columns: positive numeric OHLC. Toga accepts lowercase columns or
  the Data module's `Open`, `High`, `Low`, and `Close` columns.
- Optional `volume`/`Volume` must be finite, numeric, and non-negative.
- Index: non-empty, unique, strictly increasing, timezone-aware
  `DatetimeIndex`. When the index is absent or timezone-naive, separate `Date`
  and `Time` columns can supply the timestamp; those values are interpreted in
  `Asia/Kolkata`.
- OHLC values must be internally consistent. Toga does not sort, deduplicate,
  resample, fill missing candles, or invent prices.

## Indicators

Use `IndicatorSpec("sma", period)`, `IndicatorSpec("ema", period)`, or
`IndicatorSpec("bollinger", period, deviations=2.0)` when making the chart.
SMA and Bollinger Bands use trailing windows. EMA uses the closes up to each
row (`adjust=False`). Values remain blank until a full warm-up period exists.
The browser controls can also add or remove indicators after the chart opens.

## Example

```python
from Engines import IndicatorSpec, Toga

chart = Toga().plot(
    candles,  # a DataFrame or DataClient CandleData
    symbol="TATASTEEL",
    timeframe="1d",
    indicators=[IndicatorSpec("sma", 20), IndicatorSpec("ema", 50)],
    save_to="Research/outputs/tata-steel.html",
)
```

Open the saved `.html` file in a browser. The chart includes candlesticks,
volume when supplied, crosshair values, wheel zoom, drag-to-pan, and an
indicator panel. `show=True` opens a temporary HTML chart in the default
browser. `TogaChart.save_html(path)` saves a returned chart, and
`TogaChart.open()` opens it. Python-calculated indicator values are available
in `chart.indicators`; SMA and EMA are Series and Bollinger output is a
DataFrame with `middle`, `upper`, and `lower` columns.

The chart shows each candle's timestamp and does not synthesize bars across
missing intervals. Indicators use only current and earlier candle closes; no
future data is used. See
[TOGA_HOWTO.md](TOGA_HOWTO.md) for a step-by-step usage guide.
