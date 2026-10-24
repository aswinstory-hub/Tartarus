# How to use Phylax engines

This guide covers the three research engines: Buroka for historical order
simulation, Kijun for realized-trade metrics and reports, and Toga for OHLC
charts and trailing indicators. The engines do not place live orders.

## Install and get candles

Install the project and development tools:

```powershell
uv sync --dev
```

For Dhan data, put `DHAN_ACCESS_TOKEN` in the project-root `.env` file or set
it in the environment of the process that runs Python. `DhanClient` loads the
project `.env` while preserving an already-set process variable. Keep the token
out of source files and notebooks. Alternatively, read an existing local
SQLite candle database with `SQLiteCandleStore`.

Both sources return `CandleData`; its `frame` is a pandas DataFrame with
`Date`, `Time`, `Open`, `High`, `Low`, `Close`, and `Volume` columns when
available. It keeps the timezone-aware `Asia/Kolkata` timestamp index for
chronological processing.

```python
from datetime import date

from Data import DhanClient, Instrument

tata_steel = Instrument(
    security_id="3499",
    exchange_segment="NSE_EQ",
    instrument="EQUITY",
    symbol="TATASTEEL",
)
candles = DhanClient().fetch(
    tata_steel, date(2025, 1, 1), date(2025, 4, 1), interval="1d"
)
frame = candles.frame
print(frame.tail())
print("duplicate timestamps:", candles.duplicate_timestamps)
```

The end date is exclusive. Confirm the security ID against Dhan's current
instrument list before relying on a symbol mapping. For a local database, use
`SQLiteCandleStore("path/to/file.db").fetch(...)` with the same instrument,
range, and interval arguments. See `Data/README.md` for its schema.

## Toga: interactive chart candles and indicators

Toga accepts a `CandleData` result or a DataFrame with a timezone-aware,
strictly increasing, unique `DatetimeIndex` and positive OHLC columns. It
accepts both the Data module's title-case columns and lowercase `open`, `high`,
`low`, and `close` columns. `volume` is optional. Invalid OHLC values, missing
values, duplicate timestamps, and unsorted candles raise `TogaDataError`.

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
    ],
    save_to="Research/outputs/tata-steel.html",
)
```

Open the saved HTML file in a browser. It is self-contained and has an
interactive candlestick chart, volume pane, hover values, zoom/pan, and
controls to add or remove SMA, EMA, and Bollinger overlays. Pass `show=True`
to open a temporary chart in your default browser. The returned object exposes
`chart.indicators` and can save/open itself with `save_html` and `open`.

Indicators are calculated from the close column only. SMA and Bollinger Bands
use trailing windows; EMA uses `adjust=False`. Each requires a full period
before returning its first value. No future candle is used. See
`Engines/TOGA_HOWTO.md` for chart controls and examples.

To calculate an indicator without plotting:

```python
sma20 = toga.calculate_indicator(frame, kind="sma", period=20)
```

Supported indicator kinds are `"sma"` and `"ema"`; periods must be positive
integers. Toga is for research visualization and does not make trading or
performance decisions.

## Buroka: simulate limit entries and exits

Buroka consumes one completed candle at a time. Process the candle first, then
evaluate signals using data available through that candle. Submit an order only
after processing; it becomes eligible on the next candle. A pre-submitted order
can be eligible on the first candle.

```python
from Engines import Buroka

broker = Buroka(
    lot_size=1,
    multiplier=1.0,
    fee_rate=0.0,
    spread_bps=0.0,
    slippage_bps=0.0,
)

for timestamp, candle in frame.iterrows():
    broker.process_candle(candle)
    # Evaluate a signal here using this completed candle and earlier candles.
    # When it fires, use readable order fields, for example:
    # broker.place_limit_order(
    #     side="buy",
    #     entry_price=float(candle["close"]),
    #     stop_loss=float(candle["close"]) * 0.98,
    #     take_profit=float(candle["close"]) * 1.04,
    #     lots=1,
    # )

snapshot = broker.finish_backtest("leave")
print(snapshot.trades)
print("open positions at end:", snapshot.positions)
print("pending entries at end:", snapshot.pending_orders)
```

For simpler order calls, use `broker.place_limit_order(side="buy",
entry_price=..., stop_loss=..., take_profit=..., lots=...)`. To request a
signal exit, call `broker.close_position_next_candle(position_id)`. The older
`submit_order`, `request_close`, `on_candle`, and `finish` methods remain
available.

Only limit entries are supported. Buy brackets require `sl < entry_price < tp`;
sell brackets require `tp < entry_price < sl`. Stops and targets may trigger on
the entry candle, with stop-first resolution if both are touched. Later gaps
through a stop use the open price; limit fills are never made worse than the
limit. Costs default to zero and must be set from explicit assumptions. The
`finish` policy makes end-of-data handling explicit: `"leave"` preserves open
state, `"cancel_pending"` cancels entries, and `"close_at_last_close"` closes
remaining positions at the last processed close. Full behavior is documented
in `Engines/BUROKA.md`.

## Kijun: summarize and save results

Pass Kijun the closed trades from Buroka. Open positions are not marked to
market. Add run metadata so reports retain the strategy, instrument, timeframe,
data range, and execution assumptions.

```python
from Engines import Kijun

kijun = Kijun()
report = kijun.review(
    snapshot,
    initial_capital=1_000_000,
    metadata={
        "strategy": "SMA crossover",
        "instrument": "TATASTEEL",
        "timeframe": "1d",
        "data_source": candles.source,
        "data_range": {
            "start_inclusive": "2025-01-01",
            "end_exclusive": "2025-04-01",
        },
        "assumptions": {"fee_rate": 0.0, "spread_bps": 0.0, "slippage_bps": 0.0},
    },
)
kijun.print_summary(report)
kijun.save(report, stem="tata-steel-sma-example")
kijun.show_dashboard(report)
```

By default, Kijun writes JSON, metrics CSV, readable text, realized equity,
drawdown, and periodic-equity CSVs under the ignored `backtestMetricsLog/`
directory. Net return and CAGR require positive initial capital; CAGR also
requires a positive test duration and ending capital. Sharpe and Sortino are
calculated only when the caller supplies periodic marked equity, the
observations per year, and the annual risk-free rate. The SMA example does not
claim mark-to-market equity, so those two ratios remain undefined for that
strategy. Turnover is entry and exit price times quantity; it does not infer a
contract multiplier.

Kijun also reports trade quality, streak, side, cost breakdown, Sharpe/Sortino
when periodic equity is provided, drawdown, recovery, exposure, turnover, and
time-underwater metrics. Its browser dashboard shows interactive equity,
drawdown, and trade P&L charts, summary cards, and downloadable trade and
metrics tables. The realized curves use closed trade exits; open positions are
not marked to market.
See `Engines/KIJUN.md` for metric definitions and limitations.

## Run the example strategy

The SMA crossover example connects Dhan or a local SQLite database to Buroka
and Kijun:

```powershell
uv run python -m Strategies.sma_crossover --start 2025-01-01 --end 2025-04-01 --end-policy leave
```

The strategy starts Kijun's dashboard automatically after each run. Its default
initial capital is 1,000,000 for return metrics; set `--initial-capital` to
another value when needed. This value does not control Buroka position sizing.

For a local database:

```powershell
uv run python -m Strategies.sma_crossover --start 2025-01-01 --end 2025-04-01 --db Data/test_data/tata_steel.db
```

`--initial-capital` affects Kijun return metrics and does not control Buroka
position sizing. `--end-policy` selects whether Buroka leaves open state
visible, cancels pending orders, or closes positions at the final candle close.
The SMA CLI fetches three times the slow-period length in calendar days before
the scored start date to warm its indicators. It does not submit orders during
that warm-up and warns if fewer than 30 warm-up candles are available with the
default slow period. The strategy's full options are available with `--help`.
Its default costs are zero, so set the fee, spread, and slippage options to
your sourced assumptions before interpreting net results. A backtest is a deterministic simulation under
the stated data and execution assumptions, not a prediction or live order.
