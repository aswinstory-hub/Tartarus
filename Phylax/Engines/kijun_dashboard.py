"""Streamlit and Plotly browser dashboard for saved Kijun reports."""

from __future__ import annotations

import atexit
import html
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

_METRIC_LABELS = {
    "total_net_pnl": "Realized net P&L",
    "net_pnl": "Net P&L",
    "marked_net_pnl": "Marked net P&L",
    "net_return_pct": "Net return",
    "cagr_pct": "CAGR",
    "maximum_drawdown_amount": "Max drawdown",
    "maximum_drawdown_pct": "Max drawdown %",
    "profit_factor": "Profit factor",
    "win_rate": "Win rate",
    "average_win": "Average win",
    "average_loss": "Average loss",
    "expectancy_per_trade": "Expectancy / trade",
    "trade_count": "Total trades",
    "total_costs": "Trading costs",
    "total_slippage_cost": "Slippage cost",
    "slippage_bps": "Slippage (bps)",
    "sharpe_ratio": "Sharpe ratio",
    "sortino_ratio": "Sortino ratio",
    "calmar_ratio": "Calmar ratio",
    "time_in_market_pct": "Exposure",
    "price_notional_turnover": "Turnover",
    "recovery_factor": "Recovery factor",
    "time_underwater_days": "Time underwater",
    "maximum_time_underwater_days": "Longest underwater",
}
_PRIMARY_METRICS = (
    "net_pnl",
    "net_return_pct",
    "cagr_pct",
    "maximum_drawdown_pct",
    "profit_factor",
    "win_rate",
    "expectancy_per_trade",
    "trade_count",
)
_SECONDARY_METRICS = (
    "profit_factor",
    "win_rate",
    "average_win",
    "average_loss",
)
_TERTIARY_METRICS = (
    "expectancy_per_trade",
    "trade_count",
    "total_costs",
    "total_slippage_cost",
)
_COLORS = {
    "background": "#0b1018",
    "panel": "#111a27",
    "grid": "#243143",
    "text": "#e7edf5",
    "muted": "#91a0b3",
    "green": "#36c99a",
    "red": "#ff6b7a",
    "blue": "#63a7ff",
    "amber": "#f4be62",
}


def _number(value: Any, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (float, int)):
        return f"{value:,.3f}{suffix}"
    return f"{value}{suffix}"


def _metric_value(key: str, metrics: dict[str, Any]) -> str:
    value = metrics.get(key)
    suffix = "%" if key.endswith("_pct") or key == "slippage_bps" else ""
    if key == "slippage_bps" and value is not None:
        suffix = " bps"
    percent_keys = (
        "net_return_pct",
        "cagr_pct",
        "maximum_drawdown_pct",
        "win_rate",
        "time_in_market_pct",
    )
    if key in percent_keys:
        if value is not None and key == "win_rate":
            value = value * 100
        elif value is not None and key == "time_in_market_pct":
            suffix = "%"
    return _number(value, suffix)


def _chart_layout(figure: go.Figure, title: str, height: int = 390) -> go.Figure:
    figure.update_layout(
        title={"text": title, "x": 0.02, "xanchor": "left", "font": {"size": 16}},
        template="plotly_dark",
        height=height,
        margin={"l": 54, "r": 24, "t": 58, "b": 48},
        paper_bgcolor=_COLORS["panel"],
        plot_bgcolor=_COLORS["panel"],
        font={"color": _COLORS["text"], "family": "Inter, Segoe UI, sans-serif"},
        hovermode="x unified",
        xaxis={"gridcolor": _COLORS["grid"], "linecolor": _COLORS["grid"], "showspikes": True},
        yaxis={
            "gridcolor": _COLORS["grid"],
            "linecolor": _COLORS["grid"],
            "zerolinecolor": _COLORS["grid"],
        },
        legend={"orientation": "h", "y": 1.02, "x": 1, "xanchor": "right"},
    )
    return figure


def equity_figure(report: dict[str, Any]) -> go.Figure | None:
    curves = report.get("curves", {})
    points = curves.get("equity_curve", [])
    if not points:
        return None
    frame = pd.DataFrame(points)
    frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna(subset=["time", "value"]).sort_values("time")
    if frame.empty:
        return None
    capital = report.get("metrics", {}).get("initial_capital")
    marked = bool(curves.get("periodic_equity_curve"))
    label = (
        "Marked-to-market account equity"
        if marked
        else "Account equity"
        if capital is not None
        else "Cumulative realized P&L"
    )
    figure = go.Figure(
        go.Scatter(
            x=frame["time"],
            y=frame["value"],
            mode="lines",
            name=label,
            line={"color": _COLORS["blue"], "width": 2.6},
            fill="tozeroy" if capital is None else None,
            fillcolor="rgba(99,167,255,0.10)" if capital is None else None,
            hovertemplate="%{x|%Y-%m-%d %H:%M}<br>%{y:,.3f}<extra></extra>",
        )
    )
    figure.update_yaxes(title_text=label, tickformat=",.3f")
    figure.update_xaxes(title_text="Candle close", rangeslider_visible=True)
    return _chart_layout(figure, "Equity Curve", 440)


def drawdown_figure(report: dict[str, Any]) -> go.Figure | None:
    points = report.get("curves", {}).get("drawdown_curve", [])
    if not points:
        return None
    frame = pd.DataFrame(points)
    frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce")
    frame = frame.dropna(subset=["time", "amount"]).sort_values("time")
    if frame.empty:
        return None
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(
        go.Scatter(
            x=frame["time"],
            y=frame["amount"],
            mode="lines",
            name="Drawdown amount",
            line={"color": _COLORS["red"], "width": 2.2},
            fill="tozeroy",
            fillcolor="rgba(255,107,122,0.14)",
            hovertemplate="%{x|%Y-%m-%d %H:%M}<br>Drawdown %{y:,.3f}<extra></extra>",
        ),
        secondary_y=False,
    )
    if "percent" in frame and frame["percent"].notna().any():
        figure.add_trace(
            go.Scatter(
                x=frame["time"],
                y=frame["percent"],
                mode="lines",
                name="Drawdown %",
                line={"color": _COLORS["amber"], "width": 1.8, "dash": "dot"},
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>Drawdown %{y:.3f}%<extra></extra>",
            ),
            secondary_y=True,
        )
    figure.update_yaxes(title_text="Amount", tickformat=",.3f", secondary_y=False)
    figure.update_yaxes(title_text="Percent", ticksuffix="%", secondary_y=True)
    figure.update_xaxes(title_text="Candle close", rangeslider_visible=True)
    return _chart_layout(figure, "Drawdown", 440)


def trades_figure(report: dict[str, Any]) -> go.Figure | None:
    trades = report.get("curves", {}).get("trades", [])
    if not trades:
        return None
    frame = pd.DataFrame(trades)
    frame["net_pnl"] = pd.to_numeric(frame.get("net_pnl"), errors="coerce")
    frame = frame.dropna(subset=["net_pnl"])
    if frame.empty:
        return None
    frame["trade"] = range(1, len(frame) + 1)
    colors = [_COLORS["green"] if pnl >= 0 else _COLORS["red"] for pnl in frame["net_pnl"]]
    figure = go.Figure(
        go.Bar(
            x=frame["trade"],
            y=frame["net_pnl"],
            marker_color=colors,
            customdata=frame[
                [column for column in ("exit_time", "side", "exit_reason") if column in frame]
            ],
            hovertemplate="Trade %{x}<br>Net P&L %{y:,.3f}<extra></extra>",
        )
    )
    figure.update_xaxes(title_text="Closed trade")
    figure.update_yaxes(title_text="Net P&L", tickformat=",.3f", zeroline=True)
    return _chart_layout(figure, "Trade P&L", 350)


def _metric_cards(metrics: dict[str, Any], keys: tuple[str, ...]) -> None:
    columns = st.columns(len(keys))
    for column, key in zip(columns, keys, strict=True):
        label = _METRIC_LABELS.get(key, key.replace("_", " ").title())
        column.metric(label, _metric_value(key, metrics), border=True)


def _metrics_table(report: dict[str, Any]) -> pd.DataFrame:
    rows = []
    metrics = report.get("metrics", {})
    for key in metrics:
        label = _METRIC_LABELS.get(key, key.replace("_", " ").title())
        rows.append(
            {"Metric": label, "Value": _metric_value(key, metrics), "Field": key}
        )
    return pd.DataFrame(rows)


def _trade_table(report: dict[str, Any]) -> pd.DataFrame:
    trades = report.get("curves", {}).get("trades", [])
    if not trades:
        return pd.DataFrame(columns=["Exit", "Side", "Entry", "Exit Price", "Net P&L", "Reason"])
    frame = pd.DataFrame(trades).rename(
        columns={
            "exit_time": "Exit",
            "entry_time": "Entry",
            "side": "Side",
            "entry_price": "Entry Price",
            "exit_price": "Exit Price",
            "quantity": "Quantity",
            "net_pnl": "Net P&L",
            "exit_reason": "Reason",
        }
    )
    return frame


def render_app(report: dict[str, Any]) -> None:
    st.markdown(
        """
        <style>
        .stApp {background:#0b1018;color:#e7edf5}
        [data-testid="stHeader"] {background:rgba(11,16,24,.9)}
        [data-testid="stSidebar"] {background:#0e1622;border-right:1px solid #243143}
        .block-container {max-width:1600px;padding-top:2rem;padding-bottom:3rem}
        .kicker {color:#63a7ff;font-size:.75rem;font-weight:700;letter-spacing:.18em}
        .hero {font-size:2rem;font-weight:700;line-height:1.1;margin:.25rem 0;color:#f2f6fb}
        .subtle {color:#91a0b3;font-size:.9rem}
        div[data-testid="stMetric"] {
            background:#111a27;border:1px solid #243143;border-radius:12px;
            padding:14px 16px
        }
        div[data-testid="stMetricLabel"] {color:#91a0b3}
        div[data-testid="stMetricValue"] {font-size:1.4rem}
        div[data-baseweb="tab-list"] {gap:10px;border-bottom:1px solid #243143}
        button[data-baseweb="tab"] {color:#91a0b3}
        </style>
        """,
        unsafe_allow_html=True,
    )

    metadata = report.get("metadata", {})
    metrics = report.get("metrics", {})
    strategy = metadata.get("strategy", "Backtest")
    symbol = metadata.get("instrument", "")
    timeframe = metadata.get("timeframe", "")
    date_range = metadata.get("data_range", {})
    start = date_range.get("start_inclusive", "")
    end = date_range.get("end_exclusive", "")

    st.markdown('<div class="kicker">PHYLAX / KIJUN</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="hero">{html.escape(str(strategy))}</div>', unsafe_allow_html=True)
    context = " · ".join(str(value) for value in (symbol, timeframe, start, end) if value)
    st.markdown(
        f'<div class="subtle">{html.escape(context or "Backtest performance review")} · '
        f'Generated {html.escape(str(report.get("generated_at", "")))}</div>',
        unsafe_allow_html=True,
    )
    if report.get("history_only"):
        if report.get("trade_export") and report.get("curves", {}).get("trades"):
            st.info(
                "This historical run stores summary metrics and trade details. "
                "Candle-level equity and drawdown curves are only kept for the latest run."
            )
        else:
            st.info(
                "This historical run stores summary metrics only. Detailed trades and "
                "candle-level curves were not exported."
            )

    st.sidebar.markdown("### Run details")
    st.sidebar.write("**Instrument**", symbol or "n/a")
    st.sidebar.write("**Timeframe**", timeframe or "n/a")
    st.sidebar.write("**Data source**", metadata.get("data_source", "n/a"))
    st.sidebar.write("**Date range**", f"{start or 'n/a'} → {end or 'n/a'}")
    st.sidebar.markdown("---")
    if report.get("curves", {}).get("periodic_equity_curve"):
        st.sidebar.caption(
            "Main equity and drawdown use candle-close marks, including open-position P&L."
        )
    else:
        st.sidebar.caption(
            "Equity and drawdown use realized closed trades; open-position P&L is excluded."
        )

    _metric_cards(metrics, _PRIMARY_METRICS[:4])
    _metric_cards(metrics, _SECONDARY_METRICS)
    _metric_cards(metrics, _TERTIARY_METRICS)

    overview_tab, trades_tab, metrics_tab = st.tabs(["Overview", "Trades", "Metrics & assumptions"])
    with overview_tab:
        equity = equity_figure(report)
        drawdown = drawdown_figure(report)
        left, right = st.columns(2)
        with left:
            if equity is None:
                st.info("No dated closed-trade equity points are available for this run.")
            else:
                st.plotly_chart(equity, width="stretch", config={"displaylogo": False})
        with right:
            if drawdown is None:
                st.info("No dated closed-trade drawdown points are available for this run.")
            else:
                st.plotly_chart(drawdown, width="stretch", config={"displaylogo": False})
        trade_chart = trades_figure(report)
        if trade_chart is not None:
            st.plotly_chart(trade_chart, width="stretch", config={"displaylogo": False})

    with trades_tab:
        st.subheader("Closed trades")
        trades = _trade_table(report)
        st.dataframe(trades, width="stretch", hide_index=True)
        if not trades.empty:
            st.download_button(
                "Download trades CSV",
                trades.to_csv(index=False).encode("utf-8"),
                file_name="kijun-trades.csv",
                mime="text/csv",
            )

    with metrics_tab:
        st.subheader("Complete metrics")
        metrics_frame = _metrics_table(report)
        st.dataframe(metrics_frame, width="stretch", hide_index=True)
        st.download_button(
            "Download metrics CSV",
            metrics_frame.to_csv(index=False).encode("utf-8"),
            file_name="kijun-metrics.csv",
            mime="text/csv",
        )
        st.subheader("Assumptions")
        assumptions = report.get("assumptions", {})
        if assumptions:
            for label, value in assumptions.items():
                with st.expander(label.replace("_", " ").title()):
                    st.write(value)
        else:
            st.info("No assumptions were included in this report.")
        st.subheader("Run metadata")
        st.json(metadata)


def load_report(report_path: str | Path) -> dict[str, Any]:
    """Read and check a saved Kijun report before showing the dashboard."""
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    if not isinstance(report, dict) or not isinstance(report.get("metrics"), dict):
        raise ValueError("The selected file is not a valid Kijun report.")
    return report


def load_history_records(history_path: str | Path) -> list[dict[str, Any]]:
    """Read compact, independent history records from a strategy JSONL file."""
    path = Path(history_path)
    if not path.is_file():
        return []
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid history record on line {line_number}.") from exc
        if not isinstance(record, dict) or not isinstance(record.get("metrics"), dict):
            raise ValueError(f"Invalid history record on line {line_number}.")
        records.append(record)
    return records


def load_selected_run(strategy_folder: str | Path, backtest_id: str) -> dict[str, Any]:
    """Load the latest full report or an older compact history entry on demand."""
    folder = Path(strategy_folder).resolve()
    latest_path = folder / "latest.json"
    if latest_path.is_file():
        latest = load_report(latest_path)
        if latest.get("backtest_id") == backtest_id:
            return latest

    record = next(
        (
            item
            for item in load_history_records(folder / "history.jsonl")
            if item.get("backtest_id") == backtest_id
        ),
        None,
    )
    if record is None:
        raise ValueError(f"Backtest {backtest_id!r} was not found in this strategy history.")

    trades = []
    trade_reference = record.get("trade_export")
    if isinstance(trade_reference, str) and trade_reference:
        trade_path = (folder / trade_reference).resolve()
        if trade_path.is_relative_to(folder) and trade_path.is_file():
            try:
                frame = pd.read_csv(trade_path)
                trades = frame.astype(object).where(pd.notna(frame), None).to_dict("records")
            except (OSError, UnicodeDecodeError, pd.errors.ParserError):
                trades = []

    return {
        "backtest_id": record.get("backtest_id"),
        "strategy_id": record.get("strategy_id"),
        "generated_at": record.get("generated_at", ""),
        "metadata": record.get("metadata", {}),
        "metrics": record["metrics"],
        "assumptions": record.get("assumptions", {}),
        "trade_export": trade_reference,
        "history_only": True,
        "curves": {
            "equity_curve": [],
            "periodic_equity_curve": [],
            "drawdown_curve": [],
            "trades": trades,
        },
    }


def render_static_html(report: dict[str, Any], view: str = "overview", width: int = 120) -> str:
    """Return an HTML snapshot for callers that need a static report page."""
    if view not in {"overview", "metrics", "equity", "drawdown", "trades"}:
        raise ValueError("unknown dashboard view")
    metadata = report.get("metadata", {})
    metrics = report.get("metrics", {})
    cards = "".join(
        f'<div class="card"><span>{html.escape(_METRIC_LABELS.get(key, key))}</span>'
        f'<strong>{html.escape(_metric_value(key, metrics))}</strong></div>'
        for key in _PRIMARY_METRICS
    )
    metric_rows = "".join(
        f"<tr><td>{html.escape(key.replace('_', ' ').title())}</td>"
        f"<td>{html.escape(_metric_value(key, metrics))}</td></tr>"
        for key, value in metrics.items()
    )
    trade_rows = "".join(
        "<tr>"
        + "".join(
            f"<td>{html.escape(str(trade.get(key, '')))}</td>"
            for key in ("exit_time", "side", "entry_price", "exit_price", "net_pnl", "exit_reason")
        )
        + "</tr>"
        for trade in report.get("curves", {}).get("trades", [])
    )
    equity = equity_figure(report)
    drawdown = drawdown_figure(report)
    equity_html = (
        equity.to_html(full_html=False, include_plotlyjs="cdn")
        if equity is not None
        else '<p>No equity points available.</p>'
    )
    drawdown_html = (
        drawdown.to_html(full_html=False, include_plotlyjs="cdn")
        if drawdown is not None
        else '<p>No drawdown points available.</p>'
    )
    strategy = html.escape(str(metadata.get("strategy", "Backtest")))
    context = html.escape(
        " · ".join(
            str(value)
            for value in (
                metadata.get("instrument", ""),
                metadata.get("timeframe", ""),
                metadata.get("data_range", {}).get("start_inclusive", ""),
                metadata.get("data_range", {}).get("end_exclusive", ""),
            )
            if value
        )
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kijun · {strategy}</title>
<style>
body {{ margin:0; background:{_COLORS['background']}; color:{_COLORS['text']};
  font:14px Inter,Segoe UI,sans-serif; padding:32px }}
main {{ max-width:{max(900, width * 10)}px; margin:auto }}
.brand {{ color:{_COLORS['blue']}; letter-spacing:.18em; font-weight:bold }}
h1 {{ margin:.4em 0 }} .muted {{ color:{_COLORS['muted']} }}
.cards {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:26px 0 }}
.card,section {{ background:{_COLORS['panel']}; border:1px solid {_COLORS['grid']};
  border-radius:12px; padding:18px; margin-bottom:16px }}
.card span {{ display:block; color:{_COLORS['muted']}; margin-bottom:10px }}
.card strong {{ font-size:1.5em }} table {{ width:100%; border-collapse:collapse }}
td,th {{ padding:10px; border-bottom:1px solid {_COLORS['grid']}; text-align:left }}
td:last-child {{ text-align:right }}
@media(max-width:800px) {{ body {{ padding:16px }}
  .cards {{ grid-template-columns:repeat(2,1fr) }} }}
</style></head><body><main>
<div class="brand">PHYLAX / KIJUN</div><h1>{strategy}</h1>
<div class="muted">{context}</div><div class="cards">{cards}</div>
<section><h2>Equity Curve</h2>{equity_html}</section>
<section><h2>Drawdown Curve</h2>{drawdown_html}</section>
<section><h2>Closed Trades</h2><table><thead><tr>
<th>Exit</th><th>Side</th><th>Entry</th><th>Exit price</th><th>Net P&amp;L</th><th>Reason</th>
</tr></thead><tbody>{trade_rows}</tbody></table></section>
<section><h2>Metrics</h2><table>{metric_rows}</table></section>
</main></body></html>"""


def main() -> None:
    st.set_page_config(page_title="Kijun · Backtest Review", page_icon="◈", layout="wide")
    report_path = os.environ.get("PHYLAX_KIJUN_REPORT")
    if not report_path:
        st.error("Kijun report path is not configured for this dashboard session.")
        st.stop()
    try:
        report = load_report(report_path)
        path = Path(report_path)
        if path.name == "latest.json":
            history = load_history_records(path.parent / "history.jsonl")
            latest_id = report.get("backtest_id")
            run_ids = []
            labels = {}
            for item in reversed(history):
                run_id = item.get("backtest_id")
                if isinstance(run_id, str) and run_id not in run_ids:
                    run_ids.append(run_id)
                    labels[run_id] = f"{item.get('generated_at', '')} · {run_id}"
            if isinstance(latest_id, str) and latest_id not in run_ids:
                run_ids.insert(0, latest_id)
            if isinstance(latest_id, str):
                labels[latest_id] = f"Latest · {latest_id}"
            if run_ids:
                selected_id = st.sidebar.selectbox(
                    "Backtest run",
                    run_ids,
                    index=run_ids.index(latest_id) if latest_id in run_ids else 0,
                    format_func=lambda run_id: labels.get(run_id, run_id),
                )
                report = load_selected_run(path.parent, selected_id)
    except (OSError, ValueError) as exc:
        st.error(f"Could not read the Kijun report: {exc}")
        st.stop()
    if os.environ.get("PHYLAX_KIJUN_DELETE_REPORT") == "1":
        atexit.register(Path(report_path).unlink, missing_ok=True)
    render_app(report)


if __name__ == "__main__":
    main()
