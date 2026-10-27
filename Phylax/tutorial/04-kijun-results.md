# Tutorial 4: Read Kijun Results

Kijun is in `Engines/kijun.py`. It calculates metrics from Buroka's trades, saves a machine-readable report, and can open a local Streamlit dashboard in Tartarus's portable Chromium.

## Send results to Kijun

```python
from Engines import Kijun

kijun = Kijun()
report = kijun.review(
    results,
    initial_capital=1_000_000,
    metadata={
        "strategy": "Example",
        "instrument": "TATASTEEL",
        "timeframe": "1d",
        "data_source": "Dhan historical data",
    },
)
kijun.print_summary(report)
report_path = kijun.save(report, strategy_id="example")
kijun.show_dashboard(report, report_path=report_path)
```

Strategies should provide periodic marked equity when they want periodic risk ratios such as Sharpe and Sortino. Kijun does not derive these ratios from a handful of trade exits. It also leaves metrics undefined when the required values or valid denominators are absent. It rounds floating-point metric values to three decimals after calculation.

`show_dashboard` starts Streamlit on a locally selected port, waits for the page to be ready, and opens the actual URL using `browser/chrome-win64/chrome.exe` from the Tartarus repository. It reuses Tartarus's Chromium profile and does not force a new window. If the executable or profile is missing, it raises an error with the expected path instead of falling back to the system browser. Direct calls to `show_dashboard` open the dashboard; the SMA strategy's `OPEN_DASHBOARD` setting controls whether its run calls this method.

## Find saved reports

By default, Kijun writes `backtests/<strategy_id>/latest.json` and appends a compact row to `history.jsonl`. Trade CSV and text summary exports are optional. The folder is generated output and is ignored by Git. The dashboard reads the report; it does not fetch candles or rerun the strategy.

To inspect the dashboard from the SMA strategy, leave `OPEN_DASHBOARD = True` near the top of `Strategies/sma_crossover.py` (currently the default), then run the strategy normally. Set it to `False` to suppress the browser launch. Review the displayed curve basis and metadata before comparing runs. See [Kijun reference](../docs/kijun.md) for all metrics and their definitions.
