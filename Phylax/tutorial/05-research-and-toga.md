# Tutorial 5: Research and Toga

Put exploration scripts and notebooks in `Research/`. Toga in `Engines/toga.py` creates interactive charts and optional indicator overlays.

## Make a chart from candles

```python
from Engines import IndicatorSpec, Toga

chart = Toga().plot(
    candles,
    symbol="TATASTEEL",
    timeframe="1d",
    indicators=[IndicatorSpec("sma", 20), IndicatorSpec("ema", 50)],
    save_to="Research/outputs/tata-steel.html",
)
```

Open the saved HTML file in your browser. It contains the chart, hover values, zoom and pan controls, volume when available, and browser-side controls for supported overlays. Use `show=True` to open a temporary chart directly.

## Calculate without plotting

```python
toga = Toga()
sma_20 = toga.calculate_indicator(candles, kind="sma", period=20)
ema_50 = toga.calculate_indicator(candles, kind="ema", period=50)
bands = toga.calculate_indicator(
    candles, kind="bollinger", period=20, deviations=2.0
)
```

Indicators use current and earlier closes only. Their initial warm-up rows remain empty; do not fill them with future values. Toga validates candle structure and will not sort, deduplicate, or synthesize bars. See [Toga reference](../docs/toga.md) and [Research workspace](../docs/research.md).
