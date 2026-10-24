import pandas as pd
import pytest

from Data import CandleData
from Engines import IndicatorSpec, Toga, TogaDataError


def _candles() -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=4, freq="D", tz="Asia/Kolkata")
    return pd.DataFrame(
        {
            "open": [10.0, 11.0, 12.0, 13.0],
            "high": [11.0, 12.0, 13.0, 14.0],
            "low": [9.0, 10.0, 11.0, 12.0],
            "close": [10.5, 11.5, 12.5, 13.5],
            "volume": [100, 120, 110, 150],
        },
        index=index,
    )


def test_sma_and_ema_are_trailing_and_warm_up_is_missing() -> None:
    data = _candles()
    toga = Toga()

    sma = toga.calculate_indicator(data, kind="sma", period=2)
    ema = toga.calculate_indicator(data, kind="ema", period=2)

    assert pd.isna(sma.iloc[0])
    assert sma.iloc[1] == 11.0
    assert pd.isna(ema.iloc[0])
    assert ema.iloc[1] == pytest.approx(11.1666666667)
    future_row = pd.DataFrame(
        {"open": [14], "high": [15], "low": [13], "close": [14.5], "volume": [1]},
        index=[data.index[-1] + pd.Timedelta(days=1)],
    )
    extended = pd.concat([data, future_row])
    assert toga.calculate_indicator(extended, kind="sma", period=2).iloc[2] == sma.iloc[2]


def test_plot_builds_interactive_html_with_indicators(tmp_path) -> None:
    frame = _candles()
    candle_data = CandleData(
        frame,
        source="test",
        symbol="TEST",
        interval="1d",
        gaps=((frame.index[1], frame.index[2]),),
    )
    output = tmp_path / "chart.html"

    chart = Toga().plot(
        candle_data,
        timeframe="1d",
        indicators=[IndicatorSpec("sma", 2)],
        save_to=output,
    )

    assert output.is_file()
    assert '<canvas id="price"' in chart.html
    assert "scroll to zoom" in chart.html
    assert "Bollinger Bands" in chart.html
    assert "Simple Moving Average (SMA)" in chart.html
    assert chart.indicators["SMA 2"].iloc[1] == 11.0
    assert "function calculate(kind,period,deviations)" in output.read_text(encoding="utf-8")


def test_toga_accepts_data_module_date_time_and_title_case_columns() -> None:
    frame = _candles().rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    frame.insert(0, "Date", frame.index.strftime("%Y-%m-%d"))
    frame.insert(1, "Time", frame.index.strftime("%H:%M:%S"))

    result = Toga().calculate_indicator(frame, kind="sma", period=2)

    assert result.iloc[1] == 11.0


def test_toga_can_rebuild_index_from_date_and_time_columns() -> None:
    frame = _candles().rename(
        columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"}
    )
    frame.insert(0, "Date", frame.index.strftime("%Y-%m-%d"))
    frame.insert(1, "Time", frame.index.strftime("%H:%M:%S"))
    frame.reset_index(drop=True, inplace=True)

    result = Toga().calculate_indicator(frame, kind="sma", period=2)

    assert result.index.tz is not None
    assert result.iloc[1] == 11.0


def test_bollinger_bands_are_trailing_and_have_full_warmup() -> None:
    values = Toga().calculate_indicator(_candles(), kind="bollinger", period=2)
    assert pd.isna(values.iloc[0]["middle"])
    assert values.iloc[1]["middle"] == 11.0
    assert values.iloc[1]["upper"] == pytest.approx(12.0)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda frame: frame.rename(columns={"close": "settle"}), "missing required"),
        (lambda frame: frame.iloc[::-1], "strictly increasing"),
        (lambda frame: frame.set_axis(frame.index.tz_localize(None)), "timezone-aware"),
        (lambda frame: frame.assign(high=1.0), "high is below"),
        (lambda frame: frame.assign(volume=-1), "volume must not be negative"),
    ],
)
def test_plot_rejects_invalid_inputs(mutate, message) -> None:
    with pytest.raises(TogaDataError, match=message):
        Toga().plot(mutate(_candles()))


def test_invalid_indicator_period_is_rejected() -> None:
    with pytest.raises(TogaDataError, match="positive integer"):
        Toga().calculate_indicator(_candles(), kind="sma", period=0)


def test_chart_requires_html_output(tmp_path) -> None:
    with pytest.raises(TogaDataError, match=".html"):
        Toga().plot(_candles(), save_to=tmp_path / "chart.png")
