from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from Engines.buroka import Buroka, BurokaError, InvalidOrderError, OrderStatus

TZ = "Asia/Kolkata"
START = pd.Timestamp("2024-01-01 09:15", tz=TZ)


def candle(
    minute: int,
    *,
    open_: float = 100,
    high: float = 101,
    low: float = 99,
    close: float = 100,
) -> dict[str, object]:
    return {
        "timestamp": START + pd.Timedelta(minutes=minute),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000,
    }


def buy_order(**overrides: object) -> dict[str, object]:
    return {
        "side": "buy",
        "entry_price": 100.0,
        "sl": 98.0,
        "tp": 104.0,
        "lots": 1,
        **overrides,
    }


def test_new_order_is_only_processed_after_current_candle() -> None:
    broker = Buroka()
    broker.on_candle(candle(0))
    order_id = broker.submit_order(buy_order())

    assert broker.pending_orders[0].order_id == order_id
    assert not broker.positions

    broker.on_candle(candle(1, high=103, low=99))

    assert len(broker.positions) == 1
    assert broker.positions[0].entry_time == START + pd.Timedelta(minutes=1)


def test_limit_gap_improvement_and_stop_gap_execution_costs() -> None:
    broker = Buroka(lot_size=10, multiplier=2, fee_rate=0.001, spread_bps=2, slippage_bps=1)
    broker.submit_order(buy_order(entry_price=100, sl=90, tp=110, lots=2))
    broker.on_candle(candle(0, open_=95, high=102, low=94, close=99))

    assert broker.positions[0].entry_price == 95
    assert broker.positions[0].quantity == 20
    with pytest.raises(InvalidOrderError, match="duplicate order for an open position"):
        broker.submit_order(buy_order(entry_price=100, sl=90, tp=110, lots=2))
    broker.on_candle(candle(1, open_=89, high=92, low=88, close=90))

    trade = broker.trades[0]
    assert trade.exit_price == 89  # stop gap fills at the worse open
    assert trade.gross_pnl == (89 - 95) * 20 * 2
    assert trade.costs == pytest.approx((95 + 89) * 20 * 2 * 0.0012)
    assert trade.net_pnl == pytest.approx(trade.gross_pnl - trade.costs)
    assert trade.exit_reason == "stop_loss"


def test_stop_wins_when_stop_and_target_both_touch_same_ohlc_bar() -> None:
    broker = Buroka()
    broker.submit_order(buy_order())
    broker.on_candle(candle(0, high=105, low=97))

    assert broker.trades[0].exit_reason == "stop_loss"
    assert broker.trades[0].exit_price == 98


def test_entry_candle_take_profit_is_allowed_and_filled_at_target() -> None:
    broker = Buroka()
    broker.submit_order(buy_order())
    broker.on_candle(candle(0, high=105, low=99))

    assert broker.trades[0].exit_reason == "take_profit"
    assert broker.trades[0].exit_price == 104


def test_order_expiry_is_after_its_last_eligible_candle() -> None:
    broker = Buroka()
    order_id = broker.submit_order(buy_order(valid_for_bars=1))
    broker.on_candle(candle(0, open_=100.5, high=101, low=100.5, close=100.75))

    assert not broker.pending_orders
    assert broker.order_history[0].order_id == order_id
    assert broker.order_history[0].status == OrderStatus.EXPIRED


def test_order_ttl_counts_while_position_limit_is_full() -> None:
    broker = Buroka(max_positions=1)
    broker.submit_order(buy_order(sl=90, tp=110))
    broker.on_candle(candle(0))
    waiting_id = broker.submit_order(
        buy_order(entry_price=95, sl=90, tp=105, valid_for_bars=1)
    )
    broker.on_candle(candle(1, open_=100, high=101, low=94, close=99))

    waiting = next(order for order in broker.order_history if order.order_id == waiting_id)
    assert waiting.status == OrderStatus.EXPIRED
    assert len(broker.positions) == 1


def test_cancel_duplicate_and_invalid_order_behaviors() -> None:
    broker = Buroka()
    order_id = broker.submit_order(buy_order())
    with pytest.raises(InvalidOrderError, match="duplicate"):
        broker.submit_order(buy_order())
    broker.cancel_order(order_id)
    assert broker.order_history[0].status == OrderStatus.CANCELLED
    with pytest.raises(InvalidOrderError, match="sl < entry_price < tp"):
        broker.submit_order(buy_order(sl=101))
    with pytest.raises(BurokaError, match="not found"):
        broker.cancel_order(order_id)


def test_signal_exit_is_filled_at_next_candle_open() -> None:
    broker = Buroka()
    broker.submit_order(buy_order(sl=90, tp=110))
    broker.on_candle(candle(0, high=102, low=99))
    position_id = broker.positions[0].position_id
    broker.request_close(position_id)
    broker.on_candle(candle(1, open_=103, high=104, low=102, close=103))

    assert broker.trades[0].exit_reason == "signal"
    assert broker.trades[0].exit_price == 103


def test_end_of_data_leave_or_close_is_explicit() -> None:
    broker = Buroka()
    broker.submit_order(buy_order(sl=90, tp=110))
    broker.on_candle(candle(0, high=102, low=99))
    snapshot = broker.finish("leave")

    assert len(snapshot.positions) == 1
    assert not snapshot.trades
    with pytest.raises(BurokaError, match="finalized"):
        broker.on_candle(candle(1))

    broker2 = Buroka()
    broker2.submit_order(buy_order(sl=90, tp=110))
    broker2.on_candle(candle(0, high=102, low=99))
    closed = broker2.finish("close_at_last_close")
    assert closed.trades[0].exit_reason == "end_of_data"
    assert closed.trades[0].exit_price == 100


def test_candle_time_must_be_aware_and_increasing() -> None:
    broker = Buroka()
    bad = candle(0)
    bad["timestamp"] = datetime(2024, 1, 1, 9, 15)
    with pytest.raises(BurokaError, match="timezone-aware"):
        broker.on_candle(bad)
    broker.on_candle(candle(1))
    with pytest.raises(BurokaError, match="strictly increasing"):
        broker.on_candle(candle(1))
