"""Backtest metrics and reporting for Buroka trade results.

Kijun reports realized trades only. It does not infer prices, fills, fees, or
capital. Return metrics are omitted unless the caller supplies initial capital.
"""

from __future__ import annotations

import csv
import json
import math
import os
import socket
import subprocess
import sys
import tempfile
import time
import webbrowser
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class BacktestReport:
    """Serializable metrics and run metadata for a backtest."""

    generated_at: str
    metadata: dict[str, Any]
    metrics: dict[str, float | int | None]
    assumptions: dict[str, str]
    curves: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: {
            "equity_curve": [],
            "periodic_equity_curve": [],
            "drawdown_curve": [],
            "trades": [],
        }
    )


class Kijun:
    """Calculate metrics and persist reports from Buroka's closed trades."""

    def review(
        self,
        results: Sequence[object] | object,
        *,
        initial_capital: float | None = None,
        periodic_equity: pd.Series | None = None,
        periods_per_year: int = 252,
        risk_free_rate: float = 0.0,
        metadata: Mapping[str, Any] | None = None,
    ) -> BacktestReport:
        """Review Buroka results directly, or a list of completed trades."""
        trades = getattr(results, "trades", results)
        if not isinstance(trades, Sequence) or isinstance(trades, (str, bytes)):
            raise TypeError("results must be a Buroka snapshot or a sequence of trades")
        return self.analyze(
            trades,
            initial_capital=initial_capital,
            periodic_equity=periodic_equity,
            periods_per_year=periods_per_year,
            risk_free_rate=risk_free_rate,
            metadata=metadata,
        )

    def analyze(
        self,
        trades: Sequence[object],
        *,
        initial_capital: float | None = None,
        periodic_equity: pd.Series | None = None,
        periods_per_year: int = 252,
        risk_free_rate: float = 0.0,
        metadata: Mapping[str, Any] | None = None,
    ) -> BacktestReport:
        if initial_capital is not None and (
            isinstance(initial_capital, bool)
            or not isinstance(initial_capital, (int, float))
            or not math.isfinite(initial_capital)
            or initial_capital <= 0
        ):
            raise ValueError("initial_capital must be finite and positive")
        if (
            isinstance(periods_per_year, bool)
            or not isinstance(periods_per_year, int)
            or periods_per_year < 1
        ):
            raise ValueError("periods_per_year must be a positive integer")
        if (
            isinstance(risk_free_rate, bool)
            or not isinstance(risk_free_rate, (int, float))
            or not math.isfinite(risk_free_rate)
            or risk_free_rate <= -1
        ):
            raise ValueError("risk_free_rate must be finite and greater than -1")
        periodic_curve, sharpe, sortino = _periodic_metrics(
            periodic_equity, periods_per_year, risk_free_rate
        )

        rows = [_trade_dict(trade) for trade in trades]
        gross = [_finite_number(row.get("gross_pnl")) for row in rows]
        net = [_finite_number(row.get("net_pnl")) for row in rows]
        costs = [_finite_number(row.get("costs")) for row in rows]
        valid_net = [value for value in net if value is not None]
        valid_gross = [value for value in gross if value is not None]
        valid_costs = [value for value in costs if value is not None]
        wins = [value for value in valid_net if value > 0]
        losses = [value for value in valid_net if value < 0]
        curves = _build_curves(rows, initial_capital, metadata)
        curves["periodic_equity_curve"] = periodic_curve
        drawdowns = [point["amount"] for point in curves["drawdown_curve"]]
        drawdown = max(drawdowns, default=0.0)
        drawdown_pcts = [
            point["percent"] for point in curves["drawdown_curve"] if point["percent"] is not None
        ]
        max_drawdown_pct = max(drawdown_pcts, default=None)
        exit_rows = _rows_with_valid_exit(rows)
        event_net = [
            _finite_number(row.get("net_pnl"))
            for row in exit_rows
            if _finite_number(row.get("net_pnl")) is not None
        ]
        wins = [value for value in valid_net if value > 0]
        losses = [value for value in valid_net if value < 0]
        gross_wins = [value for value in valid_gross if value > 0]
        gross_losses = [value for value in valid_gross if value < 0]
        net_profit = sum(wins)
        net_loss = abs(sum(losses))
        average_win = _mean(wins)
        average_loss = _mean(losses)
        streaks = _maximum_streaks(event_net)
        exposure = _time_in_market_pct(rows, metadata)
        fee_cost, spread_cost, slippage_cost, slippage_bps = _cost_breakdown(rows, metadata)
        underwater_total, underwater_max = _underwater_durations(
            curves["drawdown_curve"], _range_bound(metadata, "end_exclusive")
        )

        cost_impact = _ratio(sum(valid_costs), sum(abs(v) for v in valid_gross))
        metrics: dict[str, float | int | None] = {
            "trade_count": len(rows),
            "trades_with_net_pnl": len(valid_net),
            "total_gross_pnl": _clean(sum(valid_gross)),
            "total_costs": _clean(sum(valid_costs)),
            "total_net_pnl": _clean(sum(valid_net)),
            "net_pnl": _clean(sum(valid_net)),
            "win_rate": _ratio(len(wins), len(valid_net)),
            "winning_trade_count": len(wins),
            "losing_trade_count": len(losses),
            "breakeven_trade_count": sum(value == 0 for value in valid_net),
            "average_win": average_win,
            "average_loss": average_loss,
            "profit_factor": _ratio(net_profit, net_loss),
            "payoff_ratio": (
                _ratio(average_win, abs(average_loss))
                if average_win is not None and average_loss is not None
                else None
            ),
            "gross_profit": _clean(sum(gross_wins)),
            "gross_loss": _clean(sum(gross_losses)),
            "best_trade": max(valid_net, default=None),
            "worst_trade": min(valid_net, default=None),
            "median_trade_pnl": _median(valid_net),
            "maximum_consecutive_wins": streaks[0],
            "maximum_consecutive_losses": streaks[1],
            "expectancy_per_trade": _mean(valid_net),
            "maximum_drawdown_amount": _clean(drawdown),
            "maximum_drawdown_pct": max_drawdown_pct,
            "maximum_drawdown_duration_days": _maximum_drawdown_duration_days(
                curves["drawdown_curve"]
            ),
            "maximum_time_underwater_days": underwater_max,
            "time_underwater_days": underwater_total,
            "initial_capital": _clean(initial_capital),
            "ending_capital": None,
            "total_return_pct": None,
            "net_return_pct": None,
            "annualized_return_pct": None,
            "cagr_pct": None,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "periods_per_year": periods_per_year if periodic_curve else None,
            "risk_free_rate": risk_free_rate if periodic_curve else None,
            "average_holding_hours": _holding_hours(rows),
            "average_cost_per_trade": _mean(valid_costs),
            "total_fee_cost": fee_cost,
            "total_spread_cost": spread_cost,
            "total_slippage_cost": slippage_cost,
            "slippage_bps": slippage_bps,
            "price_notional_turnover": _turnover(rows),
            "time_in_market_pct": exposure,
            "long_trade_count": sum(row.get("side") == "buy" for row in rows),
            "short_trade_count": sum(row.get("side") == "sell" for row in rows),
            "long_net_pnl": _side_net_pnl(rows, "buy"),
            "short_net_pnl": _side_net_pnl(rows, "sell"),
            "recovery_factor": _ratio(sum(valid_net), drawdown),
            "calmar_ratio": None,
            "costs_as_pct_of_gross_pnl": cost_impact * 100 if cost_impact is not None else None,
        }

        if initial_capital is not None:
            ending = initial_capital + sum(valid_net)
            metrics["ending_capital"] = _clean(ending)
            total_return = _ratio(ending - initial_capital, initial_capital)
            metrics["total_return_pct"] = total_return * 100 if total_return is not None else None
            metrics["net_return_pct"] = metrics["total_return_pct"]
            duration_days = _metadata_duration_days(metadata) or _duration_days(rows)
            if duration_days and ending > 0:
                try:
                    annualized = ((ending / initial_capital) ** (365.25 / duration_days) - 1) * 100
                except OverflowError:
                    annualized = math.inf
                if math.isfinite(annualized):
                    metrics["annualized_return_pct"] = _clean(annualized)
                    metrics["cagr_pct"] = _clean(annualized)
                    if max_drawdown_pct and max_drawdown_pct > 0:
                        metrics["calmar_ratio"] = _ratio(annualized, max_drawdown_pct)

        return BacktestReport(
            generated_at=datetime.now(UTC).isoformat(),
            metadata=_json_safe(dict(metadata or {})),
            metrics=metrics,
            assumptions={
                "pnl": "Uses realized Buroka trade P&L; open positions are excluded.",
                "costs": "Uses costs reported by Buroka; no additional fees are inferred.",
                "drawdown": "Computed from cumulative realized net P&L in exit-time order.",
                "equity_curve": (
                    "Trade-exit event curve, not mark-to-market. Without initial capital, values "
                    "are cumulative realized P&L starting at zero."
                ),
                "drawdown_pct": (
                    "Uses the previous realized-equity peak and is only reported when positive "
                    "initial capital was supplied."
                ),
                "exposure": (
                    "Union of closed-trade holding intervals divided by the metadata data range; "
                    "when unavailable, closed-trade span is used. Open positions are excluded."
                ),
                "return": (
                    "Return needs positive initial_capital. Annualization uses the metadata range "
                    "when supplied; otherwise it uses first-to-last trade timestamps."
                ),
                "turnover": (
                    "Entry and exit price times quantity; no contract multiplier is inferred."
                ),
                "sharpe_sortino": (
                    "Calculated only from caller-supplied periodic marked equity; annual "
                    "risk-free rate and periods per year are explicit inputs. Undefined when "
                    "there are too few observations or no return variation/downside."
                ),
                "cost_breakdown": (
                    "Total costs come from Buroka. Fee, spread, and slippage components are "
                    "calculated from configured rates and executed notionals when metadata "
                    "contains those settings; otherwise components remain undefined."
                ),
                "underwater_time": (
                    "Calendar duration below prior realized-equity peaks between closed trades; "
                    "an open underwater period ends at metadata end_exclusive when available."
                ),
            },
            curves=curves,
        )

    def save(
        self,
        report: BacktestReport,
        *,
        output_dir: str | Path = "backtestMetricsLog",
        stem: str = "backtest",
    ) -> tuple[Path, Path, Path]:
        """Write JSON, metrics, equity, drawdown, and readable text reports."""
        if not stem or any(char in stem for char in '\\/:*?"<>|'):
            raise ValueError("stem must be a plain filename component")
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        json_path, csv_path, text_path = (
            folder / f"{stem}.json",
            folder / f"{stem}.csv",
            folder / f"{stem}.txt",
        )
        equity_path = folder / f"{stem}-equity.csv"
        periodic_equity_path = folder / f"{stem}-periodic-equity.csv"
        drawdown_path = folder / f"{stem}-drawdown.csv"
        payload = asdict(report)
        json_path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(("metric", "value"))
            writer.writerows(report.metrics.items())
        with equity_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(("time", "equity"))
            writer.writerows(
                (point["time"], point["value"]) for point in report.curves["equity_curve"]
            )
        with periodic_equity_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(("time", "equity"))
            writer.writerows(
                (point["time"], point["value"])
                for point in report.curves.get("periodic_equity_curve", [])
            )
        with drawdown_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(("time", "drawdown_amount", "drawdown_pct"))
            writer.writerows(
                (point["time"], point["amount"], point["percent"])
                for point in report.curves["drawdown_curve"]
            )
        lines = ["Backtest report", f"Generated at: {report.generated_at}", "", "Metadata:"]
        lines.extend(f"  {key}: {value}" for key, value in report.metadata.items())
        lines.extend(("", "Metrics:"))
        lines.extend(f"  {key}: {value}" for key, value in report.metrics.items())
        lines.extend(("", "Assumptions:"))
        lines.extend(f"  {key}: {value}" for key, value in report.assumptions.items())
        text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return json_path, csv_path, text_path

    def print_summary(self, report: BacktestReport) -> None:
        """Print a concise summary without formatting undefined metrics as zero."""
        print("Backtest summary")
        for key in (
            "trade_count",
            "total_gross_pnl",
            "total_costs",
            "total_fee_cost",
            "total_spread_cost",
            "total_slippage_cost",
            "total_net_pnl",
            "net_return_pct",
            "win_rate",
            "profit_factor",
            "payoff_ratio",
            "expectancy_per_trade",
            "maximum_drawdown_amount",
            "maximum_drawdown_pct",
            "time_underwater_days",
            "maximum_time_underwater_days",
            "total_return_pct",
            "cagr_pct",
            "sharpe_ratio",
            "sortino_ratio",
            "calmar_ratio",
            "recovery_factor",
            "time_in_market_pct",
            "price_notional_turnover",
            "annualized_return_pct",
        ):
            print(f"{key}: {report.metrics[key]}")

    def render_dashboard(
        self, report: BacktestReport, *, view: str = "overview", width: int | None = None
    ) -> str:
        """Render a browser-friendly HTML snapshot of the Kijun results."""
        from Engines.kijun_dashboard import render_static_html

        return render_static_html(asdict(report), view, width or 120)

    def show_dashboard(
        self, report: BacktestReport, *, report_path: str | Path | None = None
    ) -> str:
        """Launch the local Streamlit results app and open it in the browser."""
        from Engines.kijun_dashboard import _available_port

        folder = Path(tempfile.gettempdir()) / "phylax-kijun"
        folder.mkdir(parents=True, exist_ok=True)
        owns_report_file = report_path is None
        if report_path is None:
            report_file = folder / f"report-{time.time_ns()}.json"
            report_file.write_text(
                json.dumps(asdict(report), indent=2, allow_nan=False), encoding="utf-8"
            )
        else:
            report_file = Path(report_path).resolve()
            if not report_file.is_file():
                raise FileNotFoundError(f"Kijun report not found: {report_file}")

        port = _available_port()
        dashboard_script = Path(__file__).with_name("kijun_dashboard.py")
        log_path = folder / f"dashboard-{port}.log"
        environment = dict(os.environ)
        environment["PHYLAX_KIJUN_REPORT"] = str(report_file)
        if owns_report_file:
            environment["PHYLAX_KIJUN_DELETE_REPORT"] = "1"
        command = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(dashboard_script),
            "--server.headless=true",
            f"--server.port={port}",
            "--browser.gatherUsageStats=false",
        ]
        with log_path.open("ab") as log_file:
            options: dict[str, Any] = {
                "cwd": Path(__file__).resolve().parents[1],
                "env": environment,
                "stdin": subprocess.DEVNULL,
                "stdout": log_file,
                "stderr": subprocess.STDOUT,
                "close_fds": True,
            }
            if os.name == "nt":
                options["creationflags"] = (
                    subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                )
            else:
                options["start_new_session"] = True
            process = subprocess.Popen(command, **options)

        url = f"http://localhost:{port}"
        deadline = time.monotonic() + 20
        ready = False
        while time.monotonic() < deadline:
            if process.poll() is not None:
                details = log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
                if owns_report_file:
                    report_file.unlink(missing_ok=True)
                raise RuntimeError(f"Kijun dashboard failed to start. Log: {details}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                    ready = True
                    break
            except OSError:
                time.sleep(0.25)
        if not ready:
            process.terminate()
            if owns_report_file:
                report_file.unlink(missing_ok=True)
            details = log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
            raise RuntimeError(f"Kijun dashboard did not become ready. Log: {details}")

        if not webbrowser.open(url):
            print(f"Kijun dashboard is running at {url}")
        else:
            print(f"Kijun dashboard opened at {url}")
        return url


def _trade_dict(trade: object) -> dict[str, Any]:
    if isinstance(trade, Mapping):
        return dict(trade)
    if is_dataclass(trade):
        return asdict(trade)
    if hasattr(trade, "__dict__"):
        return vars(trade)
    raise TypeError("each trade must be a mapping, dataclass, or object with attributes")


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _clean(value: float | int | None) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    return float(value) if math.isfinite(value) else None


def _mean(values: Sequence[float]) -> float | None:
    return _clean(sum(values) / len(values)) if values else None


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return _clean(ordered[middle])
    return _clean((ordered[middle - 1] + ordered[middle]) / 2)


def _ratio(numerator: float, denominator: float) -> float | None:
    if not denominator or not math.isfinite(numerator / denominator):
        return None
    return _clean(numerator / denominator)


def _periodic_metrics(
    equity: pd.Series | None, periods_per_year: int, annual_risk_free_rate: float
) -> tuple[list[dict[str, Any]], float | None, float | None]:
    """Calculate annualized risk ratios from caller-supplied marked equity observations."""
    if equity is None:
        return [], None, None
    if not isinstance(equity, pd.Series):
        raise TypeError("periodic_equity must be a pandas Series indexed by observation time")
    if equity.empty or equity.isna().any():
        raise ValueError("periodic_equity must contain non-missing equity values")
    values = pd.to_numeric(equity, errors="coerce").astype(float)
    if not values.map(math.isfinite).all() or (values <= 0).any():
        raise ValueError("periodic_equity values must be finite and positive")
    if not values.index.is_monotonic_increasing or values.index.has_duplicates:
        raise ValueError("periodic_equity index must be strictly increasing and unique")

    curve = [
        {"time": _json_safe(timestamp), "value": _clean(value)}
        for timestamp, value in values.items()
    ]
    returns = values.pct_change().dropna()
    if not returns.map(math.isfinite).all():
        raise ValueError("periodic_equity produces non-finite returns")
    if len(returns) < 2:
        return curve, None, None

    period_risk_free_rate = (1 + annual_risk_free_rate) ** (1 / periods_per_year) - 1
    excess = returns - period_risk_free_rate
    deviation = float(excess.std(ddof=1))
    sharpe = (
        _clean(float(excess.mean()) / deviation * math.sqrt(periods_per_year))
        if deviation > 0
        else None
    )
    downside_deviation = math.sqrt(float((excess.clip(upper=0) ** 2).mean()))
    sortino = (
        _clean(float(excess.mean()) / downside_deviation * math.sqrt(periods_per_year))
        if downside_deviation > 0
        else None
    )
    return curve, sharpe, sortino


def _cost_breakdown(
    rows: Sequence[Mapping[str, Any]], metadata: Mapping[str, Any] | None
) -> tuple[float | None, float | None, float | None, float | None]:
    """Split configured Buroka cost assumptions without guessing missing settings."""
    if metadata is None:
        return None, None, None, None
    assumptions = metadata.get("costs_and_fill_assumptions", {})
    broker = metadata.get("broker_settings", {})
    if not isinstance(assumptions, Mapping) or not isinstance(broker, Mapping):
        return None, None, None, None
    fee_rate = _finite_number(assumptions.get("fee_rate"))
    spread_bps = _finite_number(assumptions.get("spread_bps"))
    slippage_bps = _finite_number(assumptions.get("slippage_bps"))
    if fee_rate is None or spread_bps is None or slippage_bps is None:
        return None, None, None, slippage_bps

    multiplier = _finite_number(broker.get("pnl_multiplier"))
    if multiplier is None:
        multiplier = 1.0
    notional = 0.0
    has_notional = False
    for row in rows:
        entry = _finite_number(row.get("entry_price"))
        exit_price = _finite_number(row.get("exit_price"))
        quantity = _finite_number(row.get("quantity"))
        if entry is not None and exit_price is not None and quantity is not None:
            notional += (entry + exit_price) * quantity * multiplier
            has_notional = True
    if not has_notional:
        zero_costs = not rows
        return (
            0.0 if zero_costs else None,
            0.0 if zero_costs else None,
            0.0 if zero_costs else None,
            slippage_bps,
        )
    return (
        _clean(notional * fee_rate),
        _clean(notional * spread_bps / 20_000),
        _clean(notional * slippage_bps / 10_000),
        slippage_bps,
    )


def _build_curves(
    rows: Sequence[Mapping[str, Any]],
    initial_capital: float | None,
    metadata: Mapping[str, Any] | None,
) -> dict[str, list[dict[str, Any]]]:
    """Build realized trade-exit equity/drawdown events, never daily mark-to-market."""
    events: list[tuple[pd.Timestamp, float]] = []
    for row in rows:
        pnl = _finite_number(row.get("net_pnl"))
        timestamp = _timestamp_utc(row.get("exit_time"))
        if pnl is not None and timestamp is not None:
            events.append((timestamp, pnl))
    events.sort(key=lambda event: event[0])

    start = _range_bound(metadata, "start_inclusive")
    if start is None and events:
        entry_times = [
            timestamp
            for row in rows
            if (timestamp := _timestamp_utc(row.get("entry_time"))) is not None
        ]
        start = min(entry_times, default=None)
    if start is None and events:
        start = events[0][0]
    if events and (start is None or events[0][0] < start):
        start = events[0][0]

    equity_curve: list[dict[str, Any]] = []
    drawdown_curve: list[dict[str, Any]] = []
    if start is not None:
        equity = float(initial_capital or 0.0)
        peak = equity
        equity_curve.append({"time": start.isoformat(), "value": equity})
        drawdown_curve.append(
            {
                "time": start.isoformat(),
                "amount": 0.0,
                "percent": 0.0 if initial_capital else None,
            }
        )
        for timestamp, pnl in events:
            equity += pnl
            peak = max(peak, equity)
            amount = max(0.0, peak - equity)
            percent = amount / peak * 100 if initial_capital is not None and peak > 0 else None
            equity_curve.append({"time": timestamp.isoformat(), "value": _clean(equity)})
            drawdown_curve.append(
                {
                    "time": timestamp.isoformat(),
                    "amount": _clean(amount),
                    "percent": _clean(percent),
                }
            )
    display_trades = []
    for row in _rows_with_valid_exit(rows):
        display_trades.append(
            _json_safe(
                {
                    key: row.get(key)
                    for key in (
                        "trade_id",
                        "side",
                        "entry_time",
                        "exit_time",
                        "entry_price",
                        "exit_price",
                        "quantity",
                        "net_pnl",
                        "exit_reason",
                    )
                }
            )
        )
    return {
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "trades": display_trades,
    }


def _rows_with_valid_exit(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        (row for row in rows if _timestamp_utc(row.get("exit_time")) is not None),
        key=lambda row: _timestamp_utc(row.get("exit_time")),
    )


def _timestamp_utc(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp):
            return None
        if stamp.tzinfo is None:
            return stamp.tz_localize("UTC")
        return stamp.tz_convert("UTC")
    except (TypeError, ValueError):
        return None


def _range_bound(metadata: Mapping[str, Any] | None, key: str) -> pd.Timestamp | None:
    if metadata is None:
        return None
    data_range = metadata.get("data_range")
    if not isinstance(data_range, Mapping):
        return None
    return _timestamp_utc(data_range.get(key))


def _maximum_streaks(values: Sequence[float]) -> tuple[int, int]:
    best_wins = best_losses = current_wins = current_losses = 0
    for value in values:
        if value > 0:
            current_wins += 1
            current_losses = 0
        elif value < 0:
            current_losses += 1
            current_wins = 0
        else:
            current_wins = current_losses = 0
        best_wins = max(best_wins, current_wins)
        best_losses = max(best_losses, current_losses)
    return best_wins, best_losses


def _maximum_drawdown_duration_days(curve: Sequence[Mapping[str, Any]]) -> float | None:
    return _underwater_durations(curve, None)[1]


def _underwater_durations(
    curve: Sequence[Mapping[str, Any]], end_time: pd.Timestamp | None
) -> tuple[float | None, float | None]:
    underwater_since: pd.Timestamp | None = None
    total = longest = 0.0
    for point in curve:
        timestamp = _timestamp_utc(point.get("time"))
        if timestamp is None:
            continue
        amount = _finite_number(point.get("amount")) or 0.0
        if amount > 0 and underwater_since is None:
            underwater_since = timestamp
        elif amount == 0 and underwater_since is not None:
            duration = max(0.0, (timestamp - underwater_since).total_seconds() / 86400)
            total += duration
            longest = max(longest, duration)
            underwater_since = None
    if underwater_since is not None and curve:
        last = end_time or _timestamp_utc(curve[-1].get("time"))
        curve_end = _timestamp_utc(curve[-1].get("time"))
        if last is not None and curve_end is not None:
            last = max(last, curve_end)
        if last is not None:
            duration = max(0.0, (last - underwater_since).total_seconds() / 86400)
            total += duration
            longest = max(longest, duration)
    if not curve:
        return None, None
    return _clean(total), _clean(longest)


def _time_in_market_pct(
    rows: Sequence[Mapping[str, Any]], metadata: Mapping[str, Any] | None
) -> float | None:
    intervals: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for row in rows:
        entry = _timestamp_utc(row.get("entry_time"))
        exit_time = _timestamp_utc(row.get("exit_time"))
        if entry is not None and exit_time is not None and exit_time > entry:
            intervals.append((entry, exit_time))
    if not intervals:
        has_range = _range_bound(metadata, "start_inclusive") and _range_bound(
            metadata, "end_exclusive"
        )
        return 0.0 if has_range else None

    start = _range_bound(metadata, "start_inclusive") or min(item[0] for item in intervals)
    end = _range_bound(metadata, "end_exclusive") or max(item[1] for item in intervals)
    total = (end - start).total_seconds()
    if total <= 0:
        return None
    clipped = sorted((max(left, start), min(right, end)) for left, right in intervals)
    merged: list[list[pd.Timestamp]] = []
    for left, right in clipped:
        if right <= left:
            continue
        if merged and left <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], right)
        else:
            merged.append([left, right])
    held = sum((right - left).total_seconds() for left, right in merged)
    return _clean(held / total * 100)


def _side_net_pnl(rows: Sequence[Mapping[str, Any]], side: str) -> float:
    values = [
        _finite_number(row.get("net_pnl"))
        for row in rows
        if row.get("side") == side and _finite_number(row.get("net_pnl")) is not None
    ]
    return _clean(sum(values))


def _holding_hours(rows: Sequence[Mapping[str, Any]]) -> float | None:
    durations = []
    for row in rows:
        try:
            start, end = pd.Timestamp(row["entry_time"]), pd.Timestamp(row["exit_time"])
            if start.tzinfo is None or end.tzinfo is None:
                continue
            hours = (end - start).total_seconds() / 3600
            if math.isfinite(hours) and hours >= 0:
                durations.append(hours)
        except (KeyError, TypeError, ValueError):
            continue
    return _mean(durations)


def _turnover(rows: Sequence[Mapping[str, Any]]) -> float | None:
    values = []
    for row in rows:
        entry = _finite_number(row.get("entry_price"))
        exit_price = _finite_number(row.get("exit_price"))
        quantity = _finite_number(row.get("quantity"))
        if entry is not None and exit_price is not None and quantity is not None:
            values.append((entry + exit_price) * quantity)
    return _clean(sum(values)) if values else None


def _duration_days(rows: Sequence[Mapping[str, Any]]) -> float | None:
    stamps = []
    for row in rows:
        try:
            stamp = pd.Timestamp(row["exit_time"])
            if stamp.tzinfo is not None and not pd.isna(stamp):
                stamps.append(stamp)
        except (KeyError, TypeError, ValueError):
            continue
    if not stamps:
        return None
    # Include entry dates so a one-trade multi-day run has the actual duration.
    for row in rows:
        try:
            stamp = pd.Timestamp(row["entry_time"])
            if stamp.tzinfo is not None and not pd.isna(stamp):
                stamps.append(stamp)
        except (KeyError, TypeError, ValueError):
            continue
    days = (max(stamps) - min(stamps)).total_seconds() / 86400
    return days if days > 0 else None


def _metadata_duration_days(metadata: Mapping[str, Any] | None) -> float | None:
    """Return the explicit backtest window length, if supplied in run metadata."""
    if metadata is None:
        return None
    data_range = metadata.get("data_range")
    if not isinstance(data_range, Mapping):
        return None
    start_value = data_range.get("start_inclusive")
    end_value = data_range.get("end_exclusive")
    if start_value is None or end_value is None:
        return None
    try:
        start, end = pd.Timestamp(start_value), pd.Timestamp(end_value)
        if pd.isna(start) or pd.isna(end):
            return None
        if start.tzinfo is None and end.tzinfo is not None:
            start = start.tz_localize(end.tzinfo)
        elif end.tzinfo is None and start.tzinfo is not None:
            end = end.tz_localize(start.tzinfo)
        days = (end - start).total_seconds() / 86400
        return days if days > 0 else None
    except (TypeError, ValueError):
        return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
