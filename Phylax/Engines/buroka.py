"""Historical limit-order and position simulator.

This module models a local backtest only. It has no live broker integration.
The strategy calls :meth:`Buroka.on_candle` with a completed candle before
evaluating signals and submitting orders; those orders are first eligible on
the next candle.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Literal

import pandas as pd

Side = Literal["buy", "sell"]
EndPolicy = Literal["leave", "cancel_pending", "close_at_last_close"]


class BurokaError(Exception):
    """Base exception for Buroka state and input errors."""


class InvalidOrderError(BurokaError, ValueError):
    """Raised when an order is malformed or conflicts with broker state."""


class OrderStatus(StrEnum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass(frozen=True)
class OrderRequest:
    side: Side
    entry_price: float
    sl: float
    tp: float
    lots: int
    valid_for_bars: int | None = None


@dataclass
class Order:
    order_id: str
    request: OrderRequest
    status: OrderStatus = OrderStatus.PENDING
    submitted_at: pd.Timestamp | None = None
    filled_at: pd.Timestamp | None = None
    fill_price: float | None = None
    bars_waited: int = 0


@dataclass
class Position:
    position_id: str
    order_id: str
    side: Side
    entry_time: pd.Timestamp
    entry_price: float
    lots: int
    quantity: int
    sl: float
    tp: float
    entry_cost: float
    close_requested: bool = False


@dataclass(frozen=True)
class Trade:
    trade_id: str
    order_id: str
    position_id: str
    side: Side
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    lots: int
    quantity: int
    gross_pnl: float
    costs: float
    net_pnl: float
    exit_reason: Literal["stop_loss", "take_profit", "signal", "end_of_data"]


@dataclass(frozen=True)
class BrokerSnapshot:
    pending_orders: tuple[Order, ...]
    positions: tuple[Position, ...]
    trades: tuple[Trade, ...]


@dataclass(frozen=True)
class _Candle:
    timestamp: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


@dataclass
class Buroka:
    """Simulate limit entries, protective exits, and explicit signal exits.

    ``fee_rate`` is a decimal commission/tax rate charged on each side's
    notional. ``spread_bps`` represents the full quoted spread and ``slippage_bps``
    an estimated adverse execution cost; both are charged on each side as
    standalone costs and do not worsen a limit fill price. Set them from the
    instrument/data source or leave at zero; no market costs are guessed.

    ``lot_size`` converts lots to units and ``multiplier`` converts price moves
    per unit into account currency. Leverage, margin, financing, exchange taxes
    beyond ``fee_rate``, partial fills, and tick-size rounding are not modeled.
    """

    lot_size: int = 1
    multiplier: float = 1.0
    fee_rate: float = 0.0
    spread_bps: float = 0.0
    slippage_bps: float = 0.0
    max_positions: int = 1
    max_pending_orders: int = 20
    _pending: list[Order] = field(default_factory=list, init=False, repr=False)
    _positions: list[Position] = field(default_factory=list, init=False, repr=False)
    _orders: list[Order] = field(default_factory=list, init=False, repr=False)
    _trades: list[Trade] = field(default_factory=list, init=False, repr=False)
    _close_requests: set[str] = field(default_factory=set, init=False, repr=False)
    _last_candle: _Candle | None = field(default=None, init=False, repr=False)
    _sequence: int = field(default=0, init=False, repr=False)
    _finished: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            isinstance(self.lot_size, bool)
            or not isinstance(self.lot_size, int)
            or self.lot_size < 1
        ):
            raise ValueError("lot_size must be a positive integer")
        for name in ("multiplier", "fee_rate", "spread_bps", "slippage_bps"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0 or (name == "multiplier" and value == 0):
                qualifier = "positive" if name == "multiplier" else "non-negative"
                raise ValueError(f"{name} must be finite and {qualifier}")
        for name in ("max_positions", "max_pending_orders"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")

    @property
    def pending_orders(self) -> tuple[Order, ...]:
        return tuple(self._pending)

    @property
    def positions(self) -> tuple[Position, ...]:
        return tuple(self._positions)

    @property
    def trades(self) -> tuple[Trade, ...]:
        return tuple(self._trades)

    @property
    def order_history(self) -> tuple[Order, ...]:
        return tuple(self._orders)

    def on_candle(self, candle: Mapping[str, object] | pd.Series) -> None:
        """Process a completed OHLC candle in the order lifecycle.

        Stops and targets for existing positions are processed first, followed
        by requested signal exits, then pending limit orders. Entry-candle
        stop/target checks are performed immediately after a pending fill.
        """
        self._ensure_active()
        parsed = _parse_candle(candle)
        if self._last_candle is not None and parsed.timestamp <= self._last_candle.timestamp:
            raise BurokaError("Candle timestamps must be strictly increasing")
        self._sequence += 1
        self._process_positions(parsed)
        self._process_pending(parsed)
        self._last_candle = parsed

    def process_candle(self, candle: Mapping[str, object] | pd.Series) -> None:
        """Plain-language name for processing the candle before its signal."""
        self.on_candle(candle)

    def place_limit_order(
        self,
        *,
        side: Side,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        lots: int,
        valid_for_bars: int | None = None,
    ) -> str:
        """Place a limit entry using readable stop-loss/take-profit names."""
        return self.submit_order(
            {
                "side": side,
                "entry_price": entry_price,
                "sl": stop_loss,
                "tp": take_profit,
                "lots": lots,
                "valid_for_bars": valid_for_bars,
            }
        )

    def close_position_next_candle(self, position_id: str) -> None:
        """Schedule an open position to close at the next candle's open."""
        self.request_close(position_id)

    def finish_backtest(self, policy: EndPolicy = "leave") -> BrokerSnapshot:
        """Finish the simulation and return trades and remaining broker state."""
        return self.finish(policy)

    def submit_order(self, order: OrderRequest | Mapping[str, object]) -> str:
        """Submit a validated limit-entry order, eligible starting next candle."""
        self._ensure_active()
        request = _parse_order(order)
        if len(self._pending) >= self.max_pending_orders:
            raise InvalidOrderError("maximum pending order count reached")
        if any(_same_request(item.request, request) for item in self._pending):
            raise InvalidOrderError("duplicate pending order")
        if any(
            _same_request(self._request_for_position(item), request)
            for item in self._positions
        ):
            raise InvalidOrderError("duplicate order for an open position")
        order_id = f"B-{len(self._orders) + 1:06d}"
        item = Order(
            order_id,
            request,
            submitted_at=self._last_candle.timestamp if self._last_candle else None,
        )
        self._orders.append(item)
        self._pending.append(item)
        return order_id

    def request_close(self, position_id: str) -> None:
        """Close an open position at the next processed candle's open."""
        self._ensure_active()
        if not any(position.position_id == position_id for position in self._positions):
            raise BurokaError(f"position {position_id!r} is not open")
        if position_id in self._close_requests:
            raise BurokaError(f"position {position_id!r} already has a close request")
        self._close_requests.add(position_id)

    def cancel_order(self, order_id: str) -> None:
        """Cancel an outstanding pending limit order."""
        self._ensure_active()
        order = next((item for item in self._pending if item.order_id == order_id), None)
        if order is None:
            raise BurokaError(f"pending order {order_id!r} was not found")
        order.status = OrderStatus.CANCELLED
        self._pending.remove(order)

    def finish(self, policy: EndPolicy = "leave") -> BrokerSnapshot:
        """Finalize a run, explicitly choosing how residual state is handled.

        ``leave`` retains pending orders and open positions in the returned
        snapshot. ``cancel_pending`` cancels pending entries but keeps positions.
        ``close_at_last_close`` cancels pending entries and closes positions at
        the last candle close. Neither policy invents a final candle or fill.
        """
        self._ensure_active()
        if policy not in ("leave", "cancel_pending", "close_at_last_close"):
            raise ValueError("policy must be leave, cancel_pending, or close_at_last_close")
        if policy in ("cancel_pending", "close_at_last_close"):
            for order in self._pending:
                order.status = OrderStatus.CANCELLED
            self._pending.clear()
        if policy == "close_at_last_close":
            if self._last_candle is None and self._positions:
                raise BurokaError("cannot close positions without a processed candle")
            if self._last_candle is not None:
                for position in tuple(self._positions):
                    self._close_position(
                        position,
                        self._last_candle.timestamp,
                        self._last_candle.close,
                        "end_of_data",
                    )
        self._finished = True
        return self.snapshot()

    def snapshot(self) -> BrokerSnapshot:
        """Return stable copies of the current results and outstanding state."""
        return BrokerSnapshot(
            tuple(replace(item) for item in self._pending),
            tuple(replace(item) for item in self._positions),
            tuple(self._trades),
        )

    def _process_positions(self, candle: _Candle) -> None:
        for position in tuple(self._positions):
            if position.position_id in self._close_requests:
                self._close_position(position, candle.timestamp, candle.open, "signal")
                self._close_requests.discard(position.position_id)
                continue
            exit_result = _exit_on_candle(position, candle)
            if exit_result is not None:
                exit_price, reason = exit_result
                self._close_position(position, candle.timestamp, exit_price, reason)

    def _process_pending(self, candle: _Candle) -> None:
        for order in tuple(self._pending):
            order.bars_waited += 1
            if len(self._positions) >= self.max_positions:
                self._expire_if_due(order)
                continue
            fill_price = _limit_fill_price(order.request, candle)
            if fill_price is not None:
                order.status = OrderStatus.FILLED
                order.filled_at = candle.timestamp
                order.fill_price = fill_price
                self._pending.remove(order)
                request = order.request
                quantity = request.lots * self.lot_size
                position_id = f"P-{len(self._trades) + len(self._positions) + 1:06d}"
                position = Position(
                    position_id,
                    order.order_id,
                    request.side,
                    candle.timestamp,
                    fill_price,
                    request.lots,
                    quantity,
                    request.sl,
                    request.tp,
                    self._cost(fill_price, quantity),
                )
                self._positions.append(position)
                entry_exit = _exit_on_candle(
                    position, candle, allow_open_gap=fill_price == candle.open
                )
                if entry_exit is not None:
                    exit_price, reason = entry_exit
                    self._close_position(position, candle.timestamp, exit_price, reason)
            else:
                self._expire_if_due(order)

    def _expire_if_due(self, order: Order) -> None:
        if (
            order.request.valid_for_bars is not None
            and order.bars_waited >= order.request.valid_for_bars
        ):
            order.status = OrderStatus.EXPIRED
            self._pending.remove(order)

    def _request_for_position(self, position: Position) -> OrderRequest:
        order = next(item for item in self._orders if item.order_id == position.order_id)
        return order.request

    def _close_position(
        self,
        position: Position,
        timestamp: pd.Timestamp,
        exit_price: float,
        reason: Literal["stop_loss", "take_profit", "signal", "end_of_data"],
    ) -> None:
        direction = 1 if position.side == "buy" else -1
        gross = (
            (exit_price - position.entry_price)
            * direction
            * position.quantity
            * self.multiplier
        )
        costs = position.entry_cost + self._cost(exit_price, position.quantity)
        trade_id = f"T-{len(self._trades) + 1:06d}"
        self._trades.append(
            Trade(
                trade_id,
                position.order_id,
                position.position_id,
                position.side,
                position.entry_time,
                timestamp,
                position.entry_price,
                exit_price,
                position.lots,
                position.quantity,
                gross,
                costs,
                gross - costs,
                reason,
            )
        )
        self._positions.remove(position)
        self._close_requests.discard(position.position_id)

    def _cost(self, price: float, quantity: int) -> float:
        notional = price * quantity * self.multiplier
        per_side_rate = self.fee_rate + (self.spread_bps / 2 + self.slippage_bps) / 10_000
        return notional * per_side_rate

    def _ensure_active(self) -> None:
        if self._finished:
            raise BurokaError("broker run is finalized")


def _parse_candle(candle: Mapping[str, object] | pd.Series) -> _Candle:
    values = dict(candle)
    timestamp = values.pop("timestamp", None)
    if timestamp is None and isinstance(candle, pd.Series):
        timestamp = candle.name
    if timestamp is None:
        raise BurokaError("candle must include a timestamp or have a timestamp index")
    stamp = pd.Timestamp(timestamp)
    if stamp.tzinfo is None:
        raise BurokaError("candle timestamp must be timezone-aware")
    numbers: dict[str, float] = {}
    for key in ("open", "high", "low", "close"):
        value = values.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BurokaError(f"candle {key} must be numeric")
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise BurokaError(f"candle {key} must be finite and positive")
        numbers[key] = number
    if numbers["high"] < max(numbers["open"], numbers["low"], numbers["close"]):
        raise BurokaError("candle high is below another OHLC price")
    if numbers["low"] > min(numbers["open"], numbers["high"], numbers["close"]):
        raise BurokaError("candle low is above another OHLC price")
    return _Candle(stamp, **numbers)


def _parse_order(order: OrderRequest | Mapping[str, object]) -> OrderRequest:
    if isinstance(order, OrderRequest):
        request = order
    else:
        try:
            request = OrderRequest(
                side=order["side"],  # type: ignore[arg-type]
                entry_price=order["entry_price"],  # type: ignore[arg-type]
                sl=order["sl"],  # type: ignore[arg-type]
                tp=order["tp"],  # type: ignore[arg-type]
                lots=order["lots"],  # type: ignore[arg-type]
                valid_for_bars=order.get("valid_for_bars"),  # type: ignore[arg-type]
            )
        except KeyError as exc:
            raise InvalidOrderError(f"missing order field: {exc.args[0]}") from None
    if request.side not in ("buy", "sell"):
        raise InvalidOrderError("side must be 'buy' or 'sell'")
    for name in ("entry_price", "sl", "tp"):
        value = getattr(request, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidOrderError(f"{name} must be numeric")
        if not math.isfinite(value) or value <= 0:
            raise InvalidOrderError(f"{name} must be finite and positive")
    if isinstance(request.lots, bool) or not isinstance(request.lots, int) or request.lots < 1:
        raise InvalidOrderError("lots must be a positive integer")
    if request.valid_for_bars is not None and (
        isinstance(request.valid_for_bars, bool)
        or not isinstance(request.valid_for_bars, int)
        or request.valid_for_bars < 1
    ):
        raise InvalidOrderError("valid_for_bars must be a positive integer when supplied")
    if request.side == "buy" and not request.sl < request.entry_price < request.tp:
        raise InvalidOrderError("buy orders require sl < entry_price < tp")
    if request.side == "sell" and not request.tp < request.entry_price < request.sl:
        raise InvalidOrderError("sell orders require tp < entry_price < sl")
    return request


def _limit_fill_price(request: OrderRequest, candle: _Candle) -> float | None:
    if request.side == "buy" and candle.low <= request.entry_price:
        return min(request.entry_price, candle.open)
    if request.side == "sell" and candle.high >= request.entry_price:
        return max(request.entry_price, candle.open)
    return None


def _exit_on_candle(
    position: Position, candle: _Candle, *, allow_open_gap: bool = True
) -> tuple[float, Literal["stop_loss", "take_profit"]] | None:
    if position.side == "buy":
        if allow_open_gap:
            if candle.open <= position.sl:
                return candle.open, "stop_loss"
            if candle.open >= position.tp:
                return candle.open, "take_profit"
        stop_hit = candle.low <= position.sl
        target_hit = candle.high >= position.tp
    else:
        if allow_open_gap:
            if candle.open >= position.sl:
                return candle.open, "stop_loss"
            if candle.open <= position.tp:
                return candle.open, "take_profit"
        stop_hit = candle.high >= position.sl
        target_hit = candle.low <= position.tp
    if stop_hit:
        return position.sl, "stop_loss"
    if target_hit:
        return position.tp, "take_profit"
    return None


def _same_request(left: OrderRequest, right: OrderRequest) -> bool:
    return left == right


