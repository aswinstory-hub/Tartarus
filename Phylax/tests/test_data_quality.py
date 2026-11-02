import pandas as pd
import pytest

from Data import CandleData
from Engines import DataQuality, DataQualityError
from Engines.data_quality import DataQualityWarning


def valid_candles() -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=2, freq="5min", tz="Asia/Kolkata")
    return pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000, 1200],
        },
        index=index,
    )


def test_accepts_valid_candles_and_source_reported_gaps() -> None:
    frame = valid_candles().rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    data = CandleData(
        frame=frame,
        source="fixture",
        symbol="TEST",
        interval="5",
        gaps=((frame.index[0], frame.index[1]),),
    )

    result = DataQuality.validate(data)
    assert list(result.columns) == ["open", "high", "low", "close", "volume"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda frame: frame.drop(columns="close"), "missing columns"),
        (lambda frame: frame.assign(close=[101.0, float("nan")]), "finite, and present"),
        (lambda frame: frame.assign(high=[98.0, 103.0]), "high is below"),
    ],
)
def test_rejects_invalid_candles(mutate, message: str) -> None:
    with pytest.raises(DataQualityError, match=message):
        DataQuality.validate(mutate(valid_candles()))


def test_rejects_conflicting_duplicates_and_reports_excluded_invalid_volume() -> None:
    frame = valid_candles()
    duplicate_frame = frame.copy()
    duplicate_frame.index = [frame.index[0], frame.index[0]]
    duplicate = CandleData(duplicate_frame, "fixture", "TEST", "5")
    invalid_volume = CandleData(
        frame, "fixture", "TEST", "5", invalid_volume_timestamps=(frame.index[0],)
    )

    with pytest.raises(DataQualityError, match="conflicting candles"):
        DataQuality.validate(duplicate)
    with pytest.warns(DataQualityWarning, match="prices are unavailable"):
        DataQuality.validate(invalid_volume)


def test_repairs_sort_order_numeric_strings_exact_duplicates_and_negative_volume() -> None:
    frame = valid_candles().iloc[::-1].astype(str)
    frame = pd.concat([frame, frame.iloc[[1]]])
    frame.iloc[0, frame.columns.get_loc("volume")] = "-5"

    with pytest.warns(DataQualityWarning, match="removed 1 exact duplicate"):
        repaired = DataQuality.validate(frame)

    assert repaired.index.is_monotonic_increasing
    assert not repaired.index.has_duplicates
    assert pd.api.types.is_numeric_dtype(repaired["close"])
    assert (repaired["volume"] >= 0).all()
