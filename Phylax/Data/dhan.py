"""On-demand Dhan historical candles and read-only SQLite fixture access.

Timestamps are normalized to Asia/Kolkata. The module only reads market data;
it has no order placement or account mutation methods.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time as monotonic_time
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv

IST = ZoneInfo("Asia/Kolkata")
BASE_URL = "https://api.dhan.co/v2"
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
INTRADAY_INTERVALS = {"1", "5", "15", "25", "60"}
_OHLC = ("open", "high", "low", "close")


class DataError(Exception):
    """Base error for invalid input, data, or local storage."""


class DhanRequestError(DataError):
    """Dhan HTTP or API response error, with no credential values included."""


@dataclass(frozen=True)
class Instrument:
    """Dhan instrument identifiers required by its chart endpoints."""

    security_id: str
    exchange_segment: str
    instrument: str
    symbol: str | None = None

    def __post_init__(self) -> None:
        for name in ("security_id", "exchange_segment", "instrument"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")


@dataclass(frozen=True)
class CandleData:
    """Normalized candles and observable data-quality findings.

    ``frame`` is indexed by timezone-aware candle timestamps in IST and has
    ``Date``, ``Time``, title-case OHLC, and optional ``Volume`` columns.
    ``Date`` and ``Time`` are local IST display columns; the original timezone-aware
    timestamp remains the index. Duplicate timestamps are retained and listed
    in ``duplicate_timestamps``. Negative-volume rows are excluded and listed in
    ``invalid_volume_timestamps``; their values are never rewritten. Missing
    intraday bars are listed in ``gaps``.
    Gap detection only compares bars within a weekday and the same local date,
    and does not infer bars across overnight/session boundaries.
    """

    frame: pd.DataFrame
    source: str
    symbol: str | None
    interval: str
    duplicate_timestamps: tuple[pd.Timestamp, ...] = ()
    gaps: tuple[tuple[pd.Timestamp, pd.Timestamp], ...] = ()
    invalid_volume_timestamps: tuple[pd.Timestamp, ...] = ()

    def to_ohlc_frame(self) -> pd.DataFrame:
        """Return a copy with engine-friendly lowercase OHLC column names."""
        frame = self.frame.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        return frame.drop(columns=["Date", "Time"], errors="ignore").copy()


class DataClient(Protocol):
    """Common read-only candle retrieval interface."""

    def fetch(
        self,
        instrument: Instrument,
        start: date | datetime,
        end: date | datetime,
        *,
        interval: str = "1d",
    ) -> CandleData: ...


def _as_ist(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=IST) if value.tzinfo is None else value.astimezone(IST)
    return datetime.combine(value, time.min, tzinfo=IST)


def _validate_range(start: date | datetime, end: date | datetime) -> tuple[datetime, datetime]:
    start_dt, end_dt = _as_ist(start), _as_ist(end)
    if start_dt >= end_dt:
        raise ValueError("start must be earlier than end")
    return start_dt, end_dt


def _normalize_payload(
    payload: object,
    *,
    source: str,
    symbol: str | None,
    interval: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> CandleData:
    if not isinstance(payload, dict):
        raise DataError("Candle response must be a JSON object")
    required = (*_OHLC, "timestamp")
    missing = [key for key in required if key not in payload]
    if missing:
        raise DataError(f"Candle response is missing fields: {', '.join(missing)}")
    if payload.get("volume") is not None and not isinstance(payload.get("volume"), list):
        raise DataError("Candle response field volume must be an array when provided")
    optional = ("volume",) if isinstance(payload.get("volume"), list) else ()
    all_fields = (*required, *optional)
    lengths = {key: len(payload[key]) for key in all_fields if isinstance(payload[key], list)}
    if len(lengths) != len(all_fields):
        raise DataError("Candle response fields must be arrays")
    if len(set(lengths.values())) != 1:
        raise DataError("Candle response arrays have unequal lengths")

    value_fields = (*_OHLC, *optional)
    frame = pd.DataFrame({key: payload[key] for key in value_fields})
    for key in value_fields:
        frame[key] = pd.to_numeric(frame[key], errors="coerce")
    if frame[list(value_fields)].isna().any().any():
        raise DataError("Candle response contains non-numeric or missing candle values")
    timestamps = pd.to_datetime(payload["timestamp"], unit="s", utc=True).tz_convert(IST)
    frame.index = pd.DatetimeIndex(timestamps, name="timestamp")
    frame = frame.sort_index(kind="stable")
    if start is not None:
        frame = frame.loc[frame.index >= start]
    if end is not None:
        frame = frame.loc[frame.index < end]
    invalid_volume_timestamps: tuple[pd.Timestamp, ...] = ()
    if "volume" in frame:
        invalid_volume = frame["volume"] < 0
        invalid_volume_timestamps = tuple(
            pd.Timestamp(timestamp) for timestamp in frame.index[invalid_volume]
        )
        if invalid_volume_timestamps:
            frame = frame.loc[~invalid_volume].copy()
    duplicate_mask = frame.index.duplicated(keep=False)
    duplicates = tuple(pd.Timestamp(ts) for ts in frame.index[duplicate_mask].unique())
    for col in ("open", "high", "low", "close"):
        if (frame[col] <= 0).any():
            raise DataError(f"Candle response contains non-positive {col} prices")
    if (frame["high"] < frame[["open", "low", "close"]].max(axis=1)).any():
        raise DataError("Candle response has a high below another OHLC price")
    if (frame["low"] > frame[["open", "high", "close"]].min(axis=1)).any():
        raise DataError("Candle response has a low above another OHLC price")
    gaps: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    if interval in INTRADAY_INTERVALS:
        step = timedelta(minutes=int(interval))
        index = frame.index
        for previous, current in zip(index[:-1], index[1:], strict=True):
            same_session_day = previous.date() == current.date() and previous.weekday() < 5
            if same_session_day and current - previous > step:
                gaps.append((pd.Timestamp(previous), pd.Timestamp(current)))
    frame.insert(0, "Date", frame.index.strftime("%Y-%m-%d"))
    frame.insert(1, "Time", frame.index.strftime("%H:%M:%S"))
    frame.rename(columns={key: key.title() for key in value_fields}, inplace=True)
    return CandleData(
        frame,
        source,
        symbol,
        interval,
        duplicates,
        tuple(gaps),
        invalid_volume_timestamps,
    )


class DhanClient:
    """Fetch historical candles from DhanHQ v2 on demand.

    Supply ``DHAN_ACCESS_TOKEN`` in the project ``.env`` file or process
    environment, or pass ``access_token``. An existing process value is not
    overwritten by the project file. Intraday queries are split into
    consecutive chunks no longer than the documented 90-day window. ``end``
    is exclusive; date-only boundaries mean midnight IST, and naive datetimes
    are interpreted as IST.
    """

    def __init__(
        self,
        access_token: str | None = None,
        *,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        load_dotenv(dotenv_path=_ENV_FILE, override=False)
        self._access_token = access_token or os.getenv("DHAN_ACCESS_TOKEN")
        if not self._access_token:
            raise ValueError("Set DHAN_ACCESS_TOKEN or pass access_token")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._last_request: float | None = None

    def fetch(
        self,
        instrument: Instrument,
        start: date | datetime,
        end: date | datetime,
        *,
        interval: str = "1d",
    ) -> CandleData:
        start_dt, end_dt = _validate_range(start, end)
        if interval != "1d" and interval not in INTRADAY_INTERVALS:
            raise ValueError("interval must be '1d', '1', '5', '15', '25', or '60'")
        chunks: list[dict[str, object]] = []
        cursor = start_dt
        while cursor < end_dt:
            chunk_end = min(cursor + timedelta(days=90), end_dt) if interval != "1d" else end_dt
            request_end = chunk_end - timedelta(seconds=1) if interval != "1d" else chunk_end
            body: dict[str, object] = {
                "securityId": instrument.security_id,
                "exchangeSegment": instrument.exchange_segment,
                "instrument": instrument.instrument,
                "oi": False,
                "fromDate": cursor.strftime(
                    "%Y-%m-%d" if interval == "1d" else "%Y-%m-%d %H:%M:%S"
                ),
                "toDate": request_end.strftime(
                    "%Y-%m-%d" if interval == "1d" else "%Y-%m-%d %H:%M:%S"
                ),
            }
            endpoint = "/charts/historical" if interval == "1d" else "/charts/intraday"
            if interval != "1d":
                body["interval"] = interval
            chunks.append(self._post(endpoint, body))
            cursor = chunk_end
        payload = _concat_payloads(chunks)
        return _normalize_payload(
            payload,
            source="dhan",
            symbol=instrument.symbol,
            interval=interval,
            start=start_dt,
            end=end_dt,
        )

    def _post(self, endpoint: str, body: dict[str, object]) -> dict[str, object]:
        # Dhan documents a five requests/second limit for Data APIs.
        now = monotonic_time.monotonic()
        if self._last_request is not None:
            wait = 0.2 - (now - self._last_request)
            if wait > 0:
                monotonic_time.sleep(wait)
        request = Request(
            f"{self._base_url}{endpoint}",
            data=json.dumps(body).encode("utf-8"),
            headers={"access-token": self._access_token or "", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = _response_error(exc.read())
            raise DhanRequestError(f"Dhan returned HTTP {exc.code}: {detail}") from None
        except (URLError, TimeoutError) as exc:
            raise DhanRequestError(f"Dhan request failed: {type(exc).__name__}") from None
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DhanRequestError(f"Dhan returned invalid JSON: {type(exc).__name__}") from None
        finally:
            self._last_request = monotonic_time.monotonic()
        if not isinstance(decoded, dict):
            raise DhanRequestError("Dhan response was not a JSON object")
        if decoded.get("status") == "failure" or "errorCode" in decoded or "errorType" in decoded:
            raise DhanRequestError(f"Dhan API error: {_response_error(decoded)}")
        return decoded


def _response_error(response: object) -> str:
    if isinstance(response, bytes):
        try:
            response = json.loads(response.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "unreadable error response"
    if isinstance(response, dict):
        parts = [
            str(response[key])
            for key in ("errorCode", "errorType", "errorMessage")
            if response.get(key)
        ]
        return ": ".join(parts) if parts else "unspecified API error"
    return "unspecified API error"


def _concat_payloads(chunks: list[dict[str, object]]) -> dict[str, list[object]]:
    keys = (*_OHLC, "timestamp")
    include_volume = bool(chunks) and all(isinstance(chunk.get("volume"), list) for chunk in chunks)
    if include_volume:
        keys = (*keys, "volume")
    result: dict[str, list[object]] = {key: [] for key in keys}
    for chunk in chunks:
        for key in keys:
            value = chunk.get(key, [])
            if not isinstance(value, list):
                raise DataError(f"Candle response field {key} must be an array")
            result[key].extend(value)
    return result


class SQLiteCandleStore:
    """Read normalized candle rows from a local SQLite database.

    Expected table ``candles`` columns: ``symbol, interval, timestamp, open,
    high, low, close, volume``. Timestamps in storage must be ISO-8601 with an
    offset, or epoch seconds. This class never creates/changes the database.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = os.fspath(path)

    def fetch(
        self,
        instrument: Instrument,
        start: date | datetime,
        end: date | datetime,
        *,
        interval: str = "1d",
    ) -> CandleData:
        start_dt, end_dt = _validate_range(start, end)
        try:
            sqlite_uri = f"{Path(self.path).resolve().as_uri()}?mode=ro"
            connection = sqlite3.connect(sqlite_uri, uri=True)
        except sqlite3.Error as exc:
            raise DataError(f"Could not open candle database: {exc}") from exc
        try:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(candles)").fetchall()
            }
            required = {"timestamp", *_OHLC}
            missing = required - columns
            if missing:
                raise DataError(f"Candle database is missing columns: {', '.join(sorted(missing))}")
            selected_columns = ["timestamp", *_OHLC]
            has_volume = "volume" in columns
            if has_volume:
                selected_columns.append("volume")
            rows = connection.execute(
                f"""SELECT {", ".join(selected_columns)} FROM candles
                   WHERE symbol = ? AND interval = ? ORDER BY timestamp""",
                (instrument.symbol or instrument.security_id, interval),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DataError(f"Could not read candle database: {exc}") from exc
        finally:
            connection.close()
        selected: list[tuple[object, ...]] = []
        for row in rows:
            stamp = _sqlite_timestamp(row[0])
            if start_dt <= stamp < end_dt:
                selected.append((stamp.timestamp(), *row[1:]))
        payload = {"timestamp": [row[0] for row in selected]}
        for position, name in enumerate(_OHLC, start=1):
            payload[name] = [row[position] for row in selected]
        if has_volume:
            payload["volume"] = [row[5] for row in selected]
        return _normalize_payload(
            payload,
            source=f"sqlite:{self.path}",
            symbol=instrument.symbol,
            interval=interval,
            start=start_dt,
            end=end_dt,
        )


def _sqlite_timestamp(value: object) -> datetime:
    if isinstance(value, (float, int)):
        return datetime.fromtimestamp(value, tz=IST)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise DataError("SQLite timestamp must be epoch seconds or ISO-8601") from exc
    return parsed.replace(tzinfo=IST) if parsed.tzinfo is None else parsed.astimezone(IST)


def fetch_candles(
    instrument: Instrument,
    start: date | datetime,
    end: date | datetime,
    *,
    interval: str = "1d",
    source: DataClient | None = None,
) -> CandleData:
    """Fetch candles with an injected client or Dhan by default."""
    client = source if source is not None else DhanClient()
    return client.fetch(instrument, start, end, interval=interval)
