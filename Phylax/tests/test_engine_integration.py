from datetime import date

import pandas as pd

from Engines import Buroka, IndicatorSpec, Kijun, Toga


def test_buroka_kijun_toga_work_together(tmp_path) -> None:
    index = pd.date_range("2025-01-01", periods=2, freq="D", tz="Asia/Kolkata")
    candles = pd.DataFrame(
        {
            "open": [100.0, 100.0],
            "high": [101.0, 105.0],
            "low": [99.0, 99.0],
            "close": [100.0, 104.0],
            "volume": [1000, 1500],
        },
        index=index,
    )

    broker = Buroka()
    broker.place_limit_order(
        side="buy", entry_price=100.0, stop_loss=98.0, take_profit=104.0, lots=1
    )
    for _, candle in candles.iterrows():
        broker.process_candle(candle)
    snapshot = broker.finish_backtest("leave")

    report = Kijun().review(
        snapshot,
        initial_capital=1000,
        metadata={
            "data_range": {
                "start_inclusive": date(2025, 1, 1),
                "end_exclusive": date(2025, 1, 3),
            }
        },
    )
    chart = Toga().plot(
        candles,
        symbol="TEST",
        timeframe="1d",
        indicators=[IndicatorSpec("sma", 1)],
        save_to=tmp_path / "integration.html",
    )

    assert len(snapshot.trades) == 1
    assert snapshot.trades[0].exit_reason == "take_profit"
    assert report.metrics["total_net_pnl"] == 4.0
    assert report.metrics["total_return_pct"] == 0.4
    assert (tmp_path / "integration.html").is_file()
    assert "<canvas id=\"price\"" in chart.html
