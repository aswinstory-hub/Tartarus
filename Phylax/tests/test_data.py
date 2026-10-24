from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from urllib.request import Request

import pandas as pd
import pytest

import Data.dhan as dhan_module
from Data.dhan import (
    IST,
    DataError,
    DhanClient,
    DhanRequestError,
    Instrument,
    SQLiteCandleStore,
    _normalize_payload,
)

TATA_STEEL = Instrument("3499", "NSE_EQ", "EQUITY", "TATASTEEL")


def test_dhan_client_loads_dotenv_without_overriding_process_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("DHAN_ACCESS_TOKEN=dotenv-token\n", encoding="utf-8")
    monkeypatch.setattr(dhan_module, "_ENV_FILE", dotenv_path)
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)

    dotenv_client = DhanClient()
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "process-token")
    process_client = DhanClient()

    assert dotenv_client._access_token == "dotenv-token"
    assert process_client._access_token == "process-token"


def _payload(timestamps: list[int] | None = None) -> dict[str, list[object]]:
    timestamps = timestamps or [1722501000, 1722501300]
    count = len(timestamps)
    return {
        "timestamp": timestamps,
        "open": [100.0] * count,
        "high": [102.0] * count,
        "low": [99.0] * count,
        "close": [101.0] * count,
        "volume": [1000] * count,
    }


def test_normalize_payload_uses_ist_and_reports_gaps_and_duplicates() -> None:
    payload = _payload([1722500100, 1722500100, 1722500400])

    data = _normalize_payload(payload, source="test", symbol="TATASTEEL", interval="1")

    assert data.frame.index.tz == IST
    assert len(data.duplicate_timestamps) == 1
    assert len(data.gaps) == 1
    assert list(data.frame.columns) == [
        "Date",
        "Time",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]
    assert data.frame.iloc[0]["Date"] == data.frame.index[0].strftime("%Y-%m-%d")
    assert data.frame.iloc[0]["Time"] == data.frame.index[0].strftime("%H:%M:%S")


@pytest.mark.parametrize(
    "payload",
    [
        {"timestamp": [1, 2], "open": [1], "high": [1, 1], "low": [1, 1], "close": [1, 1]},
        {**_payload(), "volume": [1]},
        {**_payload(), "high": [98.0, 98.0]},
    ],
)
def test_normalize_payload_rejects_malformed_candles(payload: dict[str, list[object]]) -> None:
    with pytest.raises(DataError):
        _normalize_payload(payload, source="test", symbol=None, interval="1d")


def test_normalize_payload_allows_missing_volume() -> None:
    payload = _payload()
    payload.pop("volume")

    result = _normalize_payload(payload, source="test", symbol=None, interval="1d")

    assert "Volume" not in result.frame.columns
    assert list(result.frame.columns) == ["Date", "Time", "Open", "High", "Low", "Close"]


def test_sqlite_store_reads_only_matching_symbol_interval_and_range(tmp_path) -> None:
    db_path = tmp_path / "fixture.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """CREATE TABLE candles (
                symbol TEXT, interval TEXT, timestamp TEXT,
                open REAL, high REAL, low REAL, close REAL, volume INTEGER
            )"""
        )
        connection.executemany(
            "INSERT INTO candles VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("TATASTEEL", "1d", "2024-08-01T00:00:00+05:30", 100, 102, 99, 101, 1000),
                ("TATASTEEL", "1d", "2024-08-02T00:00:00+05:30", 101, 103, 100, 102, 1100),
                ("OTHER", "1d", "2024-08-01T00:00:00+05:30", 1, 2, 0.5, 1.5, 20),
            ],
        )

    data = SQLiteCandleStore(db_path).fetch(TATA_STEEL, date(2024, 8, 1), date(2024, 8, 2))

    assert len(data.frame) == 1
    assert data.frame.iloc[0]["Close"] == 101
    assert data.frame.index[0] == pd.Timestamp(datetime(2024, 8, 1, tzinfo=IST))
    assert data.source.startswith("sqlite:")


def test_sqlite_store_allows_schema_without_volume(tmp_path) -> None:
    db_path = tmp_path / "without-volume.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """CREATE TABLE candles (
                symbol TEXT, interval TEXT, timestamp TEXT,
                open REAL, high REAL, low REAL, close REAL
            )"""
        )
        connection.execute(
            "INSERT INTO candles VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("TATASTEEL", "1d", "2024-08-01T00:00:00+05:30", 100, 102, 99, 101),
        )

    data = SQLiteCandleStore(db_path).fetch(TATA_STEEL, date(2024, 8, 1), date(2024, 8, 2))

    assert "Volume" not in data.frame.columns
    assert data.frame.iloc[0]["Close"] == 101


def test_dhan_client_sends_documented_intraday_request(monkeypatch) -> None:
    requests: list[Request] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return json.dumps(_payload()).encode()

    def fake_urlopen(request: Request, timeout: float):
        requests.append(request)
        assert timeout == 30.0
        return Response()

    monkeypatch.setattr("Data.dhan.urlopen", fake_urlopen)
    client = DhanClient("test-token")

    result = client.fetch(
        TATA_STEEL,
        datetime(2024, 8, 1, 9, 15, tzinfo=IST),
        datetime(2024, 8, 2, 15, 30, tzinfo=IST),
        interval="5",
    )

    assert result.source == "dhan"
    assert len(result.frame) == 2
    assert result.frame.index.min() >= pd.Timestamp(datetime(2024, 8, 1, 9, 15, tzinfo=IST))
    assert requests[0].full_url.endswith("/charts/intraday")
    assert requests[0].get_header("Access-token") == "test-token"
    body = json.loads(requests[0].data)
    assert body["securityId"] == "3499"
    assert body["exchangeSegment"] == "NSE_EQ"
    assert body["instrument"] == "EQUITY"
    assert body["interval"] == "5"


def test_dhan_client_splits_intraday_requests_to_90_day_windows(monkeypatch) -> None:
    requests: list[Request] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return json.dumps(_payload([])).encode()

    def fake_urlopen(request: Request, timeout: float):
        requests.append(request)
        return Response()

    monkeypatch.setattr("Data.dhan.urlopen", fake_urlopen)
    client = DhanClient("test-token")

    client.fetch(
        TATA_STEEL,
        datetime(2024, 1, 1, tzinfo=IST),
        datetime(2024, 7, 1, tzinfo=IST),
        interval="60",
    )

    assert len(requests) == 3


def test_dhan_client_requires_token_and_rejects_bad_interval(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(dhan_module, "_ENV_FILE", tmp_path / "missing.env")
    with pytest.raises(ValueError, match="DHAN_ACCESS_TOKEN"):
        DhanClient("")
    client = DhanClient("test-token")
    with pytest.raises(ValueError, match="interval"):
        client.fetch(TATA_STEEL, date(2024, 1, 1), date(2024, 1, 2), interval="2")


def test_dhan_error_does_not_echo_credentials(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return b'{"errorCode":"DH-905","errorMessage":"invalid token"}'

    monkeypatch.setattr("Data.dhan.urlopen", lambda *_args, **_kwargs: Response())
    client = DhanClient("secret-value")
    with pytest.raises(DhanRequestError) as error:
        client._post("/charts/historical", {})
    assert "invalid token" in str(error.value)
    assert "secret-value" not in str(error.value)
