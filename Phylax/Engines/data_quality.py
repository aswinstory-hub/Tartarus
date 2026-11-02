"""Normalize and safely repair historical candle data before backtests."""

from __future__ import annotations

import math
import warnings

import pandas as pd

from Data.dhan import CandleData


class DataQualityError(ValueError):
    """Raised when candle data cannot be repaired without guessing values."""


class DataQualityWarning(UserWarning):
    """Reported when safe repairs or source exclusions affect candle data."""


class DataQuality:
    """Return normalized candles, repairing deterministic issues and rejecting the rest."""

    @staticmethod
    def validate(candles: pd.DataFrame | CandleData) -> pd.DataFrame:
        """Validate and return clean lowercase OHLC data in timestamp order."""
        notes: list[str] = []
        if isinstance(candles, CandleData):
            if candles.invalid_volume_timestamps:
                notes.append(
                    f"source excluded {len(candles.invalid_volume_timestamps)} row(s) "
                    "with negative volume; their prices are unavailable"
                )
            frame = candles.frame
        elif isinstance(candles, pd.DataFrame):
            frame = candles
        elif callable(getattr(candles, "to_ohlc_frame", None)):
            frame = candles.to_ohlc_frame()
        else:
            raise DataQualityError("candles must be a pandas DataFrame or CandleData")

        frame = (
            frame.rename(
                columns={
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )
            .drop(columns=["Date", "Time"], errors="ignore")
            .copy()
        )
        required = {"open", "high", "low", "close"}
        missing = required - set(frame.columns)
        if missing:
            raise DataQualityError(f"candles missing columns: {', '.join(sorted(missing))}")
        if frame.empty:
            raise DataQualityError("candle data is empty")
        if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
            raise DataQualityError("candles must have a timezone-aware DatetimeIndex")
        if frame.index.isna().any():
            raise DataQualityError("candle timestamps must not be missing")

        if not frame.index.is_monotonic_increasing:
            frame = frame.sort_index(kind="stable")
            notes.append("sorted candles by timestamp")

        columns = list(required) + (["volume"] if "volume" in frame.columns else [])
        for column in columns:
            converted = pd.to_numeric(frame[column], errors="coerce")
            if converted.isna().any() or not converted.map(math.isfinite).all():
                raise DataQualityError(f"{column} values must be numeric, finite, and present")
            frame[column] = converted

        duplicated = frame.index.duplicated(keep=False)
        if duplicated.any():
            duplicate_rows = frame.loc[duplicated]
            if duplicate_rows.duplicated(keep=False).any():
                unique_rows = frame.drop_duplicates(keep="first")
                removed = len(frame) - len(unique_rows)
                frame = unique_rows
                notes.append(f"removed {removed} exact duplicate row(s)")
            remaining_duplicates = frame.index.duplicated(keep=False)
            if remaining_duplicates.any():
                raise DataQualityError("conflicting candles share a timestamp")

        if "volume" in frame.columns and (frame["volume"] < 0).any():
            invalid_volume = frame["volume"] < 0
            removed = int(invalid_volume.sum())
            frame = frame.loc[~invalid_volume].copy()
            notes.append(f"removed {removed} row(s) with negative volume")
            if frame.empty:
                raise DataQualityError("no candles remain after removing negative-volume rows")

        prices = frame[["open", "high", "low", "close"]]
        if (prices <= 0).any().any():
            raise DataQualityError("OHLC prices must be positive")
        if (prices["high"] < prices[["open", "low", "close"]].max(axis=1)).any():
            raise DataQualityError("candle high is below another OHLC price")
        if (prices["low"] > prices[["open", "high", "close"]].min(axis=1)).any():
            raise DataQualityError("candle low is above another OHLC price")
        if notes:
            warnings.warn(
                "Data quality repairs: " + "; ".join(notes),
                DataQualityWarning,
                stacklevel=2,
            )
        return frame
