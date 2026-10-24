"""Interactive, self-contained OHLC charts and causal indicators for research."""

# The long HTML template below contains compact CSS and JavaScript source.
# ruff: noqa: E501

from __future__ import annotations

import json
import math
import tempfile
import webbrowser
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Literal

import pandas as pd

from Data.dhan import CandleData

IndicatorKind = Literal["sma", "ema", "bollinger"]


class TogaDataError(ValueError):
    """Raised when chart or indicator input is malformed."""


@dataclass(frozen=True)
class IndicatorSpec:
    """A trailing close-price indicator, such as ``IndicatorSpec("sma", 20)``."""

    kind: IndicatorKind
    period: int
    deviations: float = 2.0


@dataclass(frozen=True)
class TogaChart:
    """Chart HTML and Python-calculated indicator values."""

    html: str
    indicators: dict[str, pd.Series | pd.DataFrame]

    def save_html(self, path: str | Path) -> Path:
        """Save the complete interactive chart as a standalone HTML file."""
        output = Path(path)
        if output.suffix.lower() not in (".html", ".htm"):
            raise TogaDataError("Toga charts must be saved as .html or .htm files")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self.html, encoding="utf-8")
        return output

    def open(self) -> Path:
        """Save a temporary standalone chart and open it in the default browser."""
        folder = Path(tempfile.gettempdir()) / "phylax-toga"
        path = self.save_html(folder / "chart.html")
        webbrowser.open(path.as_uri())
        return path


class Toga:
    """Validate, calculate indicators, and create an interactive browser chart."""

    def calculate_indicator(
        self,
        candles: pd.DataFrame | CandleData,
        *,
        kind: IndicatorKind,
        period: int,
        deviations: float = 2.0,
    ) -> pd.Series | pd.DataFrame:
        """Calculate a trailing SMA, EMA, or Bollinger Band without future data."""
        frame = _validated_frame(candles)
        _validate_indicator(kind, period, deviations)
        close = frame["close"].astype(float)
        if kind == "sma":
            return close.rolling(period, min_periods=period).mean().rename(f"SMA {period}")
        if kind == "ema":
            return (
                close.ewm(span=period, adjust=False, min_periods=period)
                .mean()
                .rename(f"EMA {period}")
            )
        middle = close.rolling(period, min_periods=period).mean()
        deviation = close.rolling(period, min_periods=period).std(ddof=0)
        return pd.DataFrame(
            {
                "middle": middle,
                "upper": middle + deviations * deviation,
                "lower": middle - deviations * deviation,
            },
            index=frame.index,
        )

    def plot(
        self,
        candles: pd.DataFrame | CandleData,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
        indicators: Sequence[IndicatorSpec] = (),
        title: str | None = None,
        show: bool = False,
        save_to: str | Path | None = None,
    ) -> TogaChart:
        """Build an interactive candlestick chart with browser-side indicators.

        Mouse-wheel zoom, drag-to-pan, crosshair values and a moving average /
        Bollinger control panel are available in the saved standalone HTML.
        """
        frame = _validated_frame(candles)
        values: dict[str, pd.Series | pd.DataFrame] = {}
        for spec in indicators:
            key = f"{spec.kind.upper()} {spec.period}"
            if spec.kind == "bollinger":
                key = f"Bollinger {spec.period} ({spec.deviations:g})"
            if key in values:
                raise TogaDataError(f"duplicate indicator overlay: {key}")
            values[key] = self.calculate_indicator(
                frame, kind=spec.kind, period=spec.period, deviations=spec.deviations
            )
        rows = []
        for timestamp, candle in frame.iterrows():
            item = {
                "time": timestamp.isoformat(),
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"]),
                "volume": float(candle["volume"]) if "volume" in frame else None,
            }
            rows.append(item)
        specs = [
            {"kind": item.kind, "period": item.period, "deviations": item.deviations}
            for item in indicators
        ]
        heading = title or " · ".join(
            part for part in (symbol, timeframe, f"{frame.index[0]} to {frame.index[-1]}") if part
        )
        html = _build_html(rows, specs, escape(heading), "volume" in frame)
        chart = TogaChart(html, values)
        if save_to is not None:
            chart.save_html(save_to)
        if show:
            chart.open()
        return chart


def _validated_frame(candles: pd.DataFrame | CandleData) -> pd.DataFrame:
    frame = candles.frame if isinstance(candles, CandleData) else candles
    if not isinstance(frame, pd.DataFrame):
        raise TogaDataError("candles must be a pandas DataFrame or CandleData")
    frame = frame.copy()
    display_names = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    frame.rename(
        columns={name: lower for name, lower in display_names.items() if name in frame.columns},
        inplace=True,
    )
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        if {"Date", "Time"}.issubset(frame.columns):
            timestamps = pd.to_datetime(
                frame["Date"].astype(str) + " " + frame["Time"].astype(str), errors="coerce"
            )
            if timestamps.isna().any():
                raise TogaDataError("Date and Time columns must contain valid candle timestamps")
            frame.index = pd.DatetimeIndex(timestamps).tz_localize("Asia/Kolkata")
    required = {"open", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise TogaDataError(f"candles missing required columns: {', '.join(sorted(missing))}")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise TogaDataError("candles must have a timezone-aware DatetimeIndex")
    if frame.empty:
        raise TogaDataError("candles must contain at least one row")
    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise TogaDataError("candle timestamps must be strictly increasing and unique")
    result = frame.copy()
    columns = [*required, *(["volume"] if "volume" in result.columns else [])]
    for column in columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
        if result[column].isna().any() or not result[column].map(math.isfinite).all():
            raise TogaDataError(f"candles contain non-numeric or non-finite {column} values")
    for column in ("open", "high", "low", "close"):
        if (result[column] <= 0).any():
            raise TogaDataError(f"candle {column} prices must be positive")
    if (result["high"] < result[["open", "low", "close"]].max(axis=1)).any():
        raise TogaDataError("candle high is below another OHLC value")
    if (result["low"] > result[["open", "high", "close"]].min(axis=1)).any():
        raise TogaDataError("candle low is above another OHLC value")
    if "volume" in result.columns and (result["volume"] < 0).any():
        raise TogaDataError("volume must not be negative")
    return result


def _validate_indicator(kind: str, period: int, deviations: float) -> None:
    if kind not in ("sma", "ema", "bollinger"):
        raise TogaDataError("indicator kind must be 'sma', 'ema', or 'bollinger'")
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise TogaDataError("indicator period must be a positive integer")
    if isinstance(deviations, bool) or not isinstance(deviations, (int, float)):
        raise TogaDataError("deviations must be a finite positive number")
    if not math.isfinite(deviations) or deviations <= 0:
        raise TogaDataError("deviations must be a finite positive number")


def _build_html(
    rows: list[dict[str, object]], specs: list[dict[str, object]], title: str, has_volume: bool
) -> str:
    safe_rows = json.dumps(rows, separators=(",", ":")).replace("<", "\\u003c")
    safe_specs = json.dumps(specs, separators=(",", ":"))
    volume_style = "" if has_volume else "#volume{display:none}"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
:root{{--bg:#131722;--panel:#1e222d;--grid:#2a2e39;--text:#d1d4dc;--muted:#787b86;--green:#26a69a;--red:#ef5350}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px Arial,sans-serif}}
header{{height:58px;display:flex;align-items:center;justify-content:space-between;padding:0 20px;border-bottom:1px solid var(--grid);background:var(--panel)}}
.brand{{font-size:18px;font-weight:bold;color:#fff}}.symbol{{margin-left:20px;color:#fff;font-weight:bold}}.hint{{color:var(--muted);font-size:12px}}
main{{display:grid;grid-template-columns:minmax(0,1fr) 270px;height:calc(100vh - 58px)}}
.chart-area{{min-width:0;display:flex;flex-direction:column;padding:12px}}#chart{{height:calc(100% - 32px);width:100%;position:relative;display:flex;flex-direction:column}}
#price{{flex:1;min-height:0}}canvas{{display:block;width:100%;height:100%}}#crosshair{{height:24px;color:var(--muted);font:12px monospace;padding:4px}}
aside{{background:var(--panel);border-left:1px solid var(--grid);padding:18px;overflow:auto}}h2{{font-size:15px;margin:0 0 16px;color:#fff}}
label{{display:block;color:var(--muted);font-size:12px;margin:13px 0 6px}}select,input,button{{width:100%;border:1px solid #363a45;background:#131722;color:var(--text);padding:9px;border-radius:4px}}
button{{margin-top:14px;background:#2962ff;border-color:#2962ff;color:#fff;cursor:pointer;font-weight:bold}}.item{{display:flex;gap:8px;align-items:center;padding:9px 0;border-bottom:1px solid var(--grid);font-size:12px}}.item span{{flex:1}}.item button{{width:auto;margin:0;background:transparent;border:0;color:var(--muted);padding:3px 6px}}
#volume{{height:80px;border-top:1px solid var(--grid)}}.legend{{color:var(--muted);font-size:12px;margin:4px}}
{volume_style}
@media(max-width:760px){{main{{grid-template-columns:1fr;grid-template-rows:minmax(0,1fr) auto}}aside{{border-left:0;border-top:1px solid var(--grid);max-height:230px}}}}
</style></head><body><header><div><span class="brand">TOGA</span><span class="symbol">{title}</span></div><div class="hint">Drag to pan · scroll to zoom · hover for values</div></header>
<main><section class="chart-area"><div id="chart"><canvas id="price"></canvas><div id="volume"><canvas id="vol"></canvas></div></div><div id="crosshair">Move over a candle to inspect OHLC values</div></section>
<aside><h2>Indicators</h2><label for="kind">Indicator</label><select id="kind"><option value="sma">Simple Moving Average (SMA)</option><option value="ema">Exponential Moving Average (EMA)</option><option value="bollinger">Bollinger Bands</option></select>
<label for="period">Period</label><input id="period" type="number" value="20" min="1" step="1"><div id="deviationBox"><label for="deviations">Standard deviations</label><input id="deviations" type="number" value="2" min="0.1" step="0.1"></div>
<button id="add">Add indicator</button><div id="indicators"></div><div class="legend">Indicators use closing prices up to each candle. Warm-up values are left blank.</div></aside></main>
<script>
const candles={safe_rows};const initialSpecs={safe_specs};
const priceCanvas=document.getElementById('price'), volumeCanvas=document.getElementById('vol');
const priceCtx=priceCanvas.getContext('2d'), volCtx=volumeCanvas.getContext('2d');
const colors=['#f7c548','#ab47bc','#42a5f5','#ff7043','#26c6da','#ec407a'];
let overlays=[], viewStart=0, viewEnd=candles.length-1, dragX=null, pointerX=null;
function resize(){{const box=priceCanvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;priceCanvas.width=box.width*dpr;priceCanvas.height=box.height*dpr;priceCtx.setTransform(dpr,0,0,dpr,0,0);const vb=volumeCanvas.getBoundingClientRect();volumeCanvas.width=vb.width*dpr;volumeCanvas.height=vb.height*dpr;volCtx.setTransform(dpr,0,0,dpr,0,0);draw()}}
function calculate(kind,period,deviations){{let output=Array(candles.length).fill(null), alpha=2/(period+1),ema=null;for(let i=0;i<candles.length;i++){{let close=candles[i].close;if(kind==='ema'){{ema=ema===null?close:close*alpha+ema*(1-alpha);if(i>=period-1)output[i]=ema}}else if(i>=period-1){{let values=candles.slice(i-period+1,i+1).map(c=>c.close),mean=values.reduce((a,b)=>a+b,0)/period;if(kind==='sma')output[i]=mean;else{{let variance=values.reduce((a,b)=>a+(b-mean)**2,0)/period,sd=Math.sqrt(variance);output[i]={{middle:mean,upper:mean+deviations*sd,lower:mean-deviations*sd}}}}}}}}return output}}
function addIndicator(spec){{let values=calculate(spec.kind,spec.period,spec.deviations),id=String(Date.now())+Math.random(),color=colors[overlays.length%colors.length];overlays.push({{...spec,values,id,color}});let row=document.createElement('div');row.className='item';row.dataset.id=id;row.innerHTML='<span></span><button title="Remove">✕</button>';row.querySelector('span').textContent=spec.kind.toUpperCase()+' '+spec.period+(spec.kind==='bollinger'?' ×'+spec.deviations:'');row.querySelector('button').onclick=()=>{{overlays=overlays.filter(o=>o.id!==id);row.remove();draw()}};document.getElementById('indicators').appendChild(row);draw()}}
function draw(){{let w=priceCanvas.clientWidth,h=priceCanvas.clientHeight;if(!w||!h)return;let ctx=priceCtx;ctx.clearRect(0,0,w,h);ctx.fillStyle='#131722';ctx.fillRect(0,0,w,h);let lo=Math.max(0,Math.floor(viewStart)),hi=Math.min(candles.length-1,Math.ceil(viewEnd)),visible=candles.slice(lo,hi+1);if(!visible.length)return;let all=visible.flatMap(c=>[c.high,c.low]);for(let o of overlays)for(let i=lo;i<=hi;i++){{let v=o.values[i];if(typeof v==='number'&&Number.isFinite(v))all.push(v);else if(v)all.push(v.upper,v.lower)}}let min=Math.min(...all),max=Math.max(...all),pad=(max-min)*.06||1;min-=pad;max+=pad;let left=62,right=w-12,top=16,bottom=h-25,cw=(right-left)/visible.length;function x(i){{return left+(i-lo+.5)*cw}}function y(v){{return bottom-(v-min)/(max-min)*(bottom-top)}}ctx.font='11px Arial';ctx.strokeStyle='#2a2e39';ctx.fillStyle='#787b86';ctx.textAlign='right';for(let n=0;n<=5;n++){{let value=max-(max-min)*n/5,yy=top+(bottom-top)*n/5;ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(right,yy);ctx.stroke();ctx.fillText(value.toFixed(2),left-8,yy+4)}}for(let i=lo;i<=hi;i++){{let c=candles[i],xx=x(i),up=c.close>=c.open;ctx.strokeStyle=ctx.fillStyle=up?'#26a69a':'#ef5350';ctx.beginPath();ctx.moveTo(xx,y(c.high));ctx.lineTo(xx,y(c.low));ctx.stroke();let body=Math.max(1,cw*.62),yy=y(Math.max(c.open,c.close)),bh=Math.max(1,Math.abs(y(c.open)-y(c.close)));ctx.fillRect(xx-body/2,yy,body,bh)}}for(let o of overlays){{ctx.strokeStyle=o.color;ctx.lineWidth=1.5;for(let key of (o.kind==='bollinger'?['upper','middle','lower']:['value'])){{ctx.beginPath();let started=false;for(let i=lo;i<=hi;i++){{let v=o.values[i],num=key==='value'?v:v&&v[key];if(num==null){{started=false;continue}}if(!started){{ctx.moveTo(x(i),y(num));started=true}}else ctx.lineTo(x(i),y(num))}}ctx.stroke()}}}}ctx.fillStyle='#787b86';ctx.textAlign='center';let count=Math.min(6,visible.length);for(let n=0;n<count;n++){{let i=lo+Math.round((hi-lo)*n/Math.max(1,count-1));ctx.fillText(candles[i].time.slice(0,10),x(i),h-5)}}drawVolume(lo,hi,left,right,cw);if(pointerX!==null){{ctx.strokeStyle='#787b86';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(pointerX,top);ctx.lineTo(pointerX,bottom);ctx.stroke();ctx.setLineDash([])}}}}
function drawVolume(lo,hi,left,right,cw){{let ctx=volCtx,w=volumeCanvas.clientWidth,h=volumeCanvas.clientHeight;ctx.clearRect(0,0,w,h);let vals=candles.slice(lo,hi+1).map(c=>c.volume||0),max=Math.max(1,...vals);for(let i=lo;i<=hi;i++){{let c=candles[i],xx=left+(i-lo+.5)*cw,v=c.volume||0;ctx.fillStyle=c.close>=c.open?'rgba(38,166,154,.55)':'rgba(239,83,80,.55)';ctx.fillRect(xx-cw*.3,h-v/max*(h-8),cw*.6,v/max*(h-8))}}}}
priceCanvas.addEventListener('mousemove',e=>{{let box=priceCanvas.getBoundingClientRect();pointerX=e.clientX-box.left;if(dragX!==null){{let delta=(e.clientX-dragX)/box.width*(viewEnd-viewStart+1);viewStart-=delta;viewEnd-=delta;dragX=e.clientX}}let index=Math.max(0,Math.min(candles.length-1,Math.round(viewStart+(pointerX-62)/(box.width-74)*(viewEnd-viewStart))));let c=candles[index];document.getElementById('crosshair').textContent=c.time+'  O '+c.open+'  H '+c.high+'  L '+c.low+'  C '+c.close+(c.volume===null?'':'  V '+c.volume);draw()}});
priceCanvas.addEventListener('mouseleave',()=>{{pointerX=null;dragX=null;draw()}});priceCanvas.addEventListener('mousedown',e=>dragX=e.clientX);window.addEventListener('mouseup',()=>dragX=null);priceCanvas.addEventListener('wheel',e=>{{e.preventDefault();let factor=e.deltaY>0?1.15:.87,span=(viewEnd-viewStart+1)*factor,center=(viewStart+viewEnd)/2;span=Math.max(8,Math.min(candles.length,span));viewStart=Math.max(0,center-span/2);viewEnd=Math.min(candles.length-1,center+span/2);draw()}},{{passive:false}});
document.getElementById('kind').onchange=e=>document.getElementById('deviationBox').style.display=e.target.value==='bollinger'?'block':'none';document.getElementById('add').onclick=()=>{{let kind=document.getElementById('kind').value,period=Number(document.getElementById('period').value),deviations=Number(document.getElementById('deviations').value);if(!Number.isInteger(period)||period<1)return alert('Period must be a positive whole number');if(kind==='bollinger'&&(!Number.isFinite(deviations)||deviations<=0))return alert('Standard deviations must be positive');addIndicator({{kind,period,deviations}})}};
initialSpecs.forEach(addIndicator);window.addEventListener('resize',resize);resize();
</script></body></html>"""
