# Toga how-to

Toga turns historical OHLC candles into an interactive HTML chart. It works
with the `CandleData` returned by `Data` or with a pandas DataFrame.

## 1. Load candle data

```python
from datetime import date

from Data import DhanClient, Instrument

instrument = Instrument(
    security_id="3499",
    exchange_segment="NSE_EQ",
    instrument="EQUITY",
    symbol="TATASTEEL",
)
candles = DhanClient().fetch(
    instrument, date(2025, 1, 1), date(2025, 4, 1), interval="1d"
)
```

The end date is exclusive. To work offline, read equivalent bars from a local
database using `SQLiteCandleStore`; Toga itself does not require Dhan access.

## 2. Make and open a chart

```python
from Engines import IndicatorSpec, Toga

toga = Toga()
chart = toga.plot(
    candles,
    symbol="TATASTEEL",
    timeframe="1d",
    indicators=[
        IndicatorSpec("sma", 20),
        IndicatorSpec("ema", 50),
        IndicatorSpec("bollinger", 20, deviations=2),
    ],
    save_to="Research/outputs/tata-steel.html",
)
```

Open `Research/outputs/tata-steel.html` in a web browser. The saved file is
self-contained, so the chart and its indicator controls work without an API
connection. Set `show=True` in `plot` to have Toga open a temporary chart in
your default browser. You can save or open the returned chart later:

```python
chart.save_html("Research/outputs/another-view.html")
chart.open()
```

## 3. Use the chart

- Hover over a candle to see its timestamp, open, high, low, close, and volume.
- Scroll over the price chart to zoom; drag to move through the visible bars.
- Choose SMA, EMA, or Bollinger Bands in the Indicators panel.
- Enter a positive period (for example, `20`), and choose the Bollinger
  standard deviation width when using Bollinger Bands.
- Select **Add indicator**. Use the × beside an indicator to remove it.

The chart displays timestamps in the timezone of the candle index. Use a
timezone-aware, sorted, unique index and complete numeric OHLC values. Toga
does not fill missing candles or change prices.

## 4. Read indicator values in Python

```python
sma_20 = toga.calculate_indicator(candles, kind="sma", period=20)
ema_50 = toga.calculate_indicator(candles, kind="ema", period=50)
bands = toga.calculate_indicator(
    candles, kind="bollinger", period=20, deviations=2.0
)
```

The results use only current and earlier closes. Initial values are missing
until the requested period is available. Bollinger Bands return `middle`,
`upper`, and `lower` columns. The chart call's Python-calculated overlays are
also available in `chart.indicators`.

See [TOGA.md](TOGA.md) for the input validation and indicator definitions.
