# Engines

All three documented engines now have Python implementations:

- `buroka.py` simulates limit entries, positions, stops/targets, and exits. It
  has no live broker integration.
- `kijun.py` calculates realized-trade metrics and persists JSON, CSV, and text
  reports.
- `toga.py` validates OHLC data and creates interactive standalone HTML charts
  with browser controls for SMA, EMA, and Bollinger Bands.

Engine behavior and assumptions:

- [Buroka](BUROKA.md)
- [Kijun](KIJUN.md)
- [Toga](TOGA.md)

See the repository [HOWTOUSE.md](../HOWTOUSE.md) for end-to-end examples.
