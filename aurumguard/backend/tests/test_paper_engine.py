from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.core.candles import Candle, Quote, Timeframe
from app.core.contract_spec import MOCK_SPEC
from app.paper.engine import OrderStatus, OrderType, PaperEngine, PaperOrder, PositionStatus, SlippageParams

UTC = UTC
T0 = datetime(2026, 3, 10, 10, 0, tzinfo=UTC)


def q(bid, ask, ts):
    return Quote("XAUUSD", bid, ask, ts, "t", ts)


def bar(i, o, h, l, c, spread=0.3):
    ts = T0 + timedelta(minutes=i)
    return Candle("XAUUSD", Timeframe.M1, ts, o, h, l, c, spread_close=spread, provider="t", ingested_at=ts + timedelta(minutes=1))


def order(direction="BUY", lots=0.1, stop=2395.0, tp1=2405.0, tp2=2410.0, otype=OrderType.MARKET, price=None, **kw):
    return PaperOrder("o1", None, "S", "1", "INTRADAY", direction, otype, lots, stop, tp1, tp2, T0 + timedelta(hours=2), T0 + timedelta(hours=8), 0.6, T0, limit_price=price, risk_usd=55.0, **kw)


def test_market_fill_bid_ask_and_slippage():
    e = PaperEngine(MOCK_SPEC, SlippageParams(0.1, 0.1, 0.15))
    e.submit(order())
    pos = e.on_quote(q(2399.85, 2400.15, T0 + timedelta(seconds=1)))
    assert len(pos) == 1 and pos[0].entry_price == pytest.approx(2400.25)  # ask + slippage
    e.submit(PaperOrder("o2", None, "S", "1", "I", "SELL", OrderType.MARKET, 0.1, 2405.0, 2395.0, 2390.0, T0 + timedelta(hours=2), None, 0.6, T0 + timedelta(seconds=2), risk_usd=55))
    pos2 = e.on_quote(q(2399.85, 2400.15, T0 + timedelta(seconds=3)))
    assert pos2[0].entry_price == pytest.approx(2399.75)  # bid - slippage


def test_reject_on_spread_and_expiry_and_ordering():
    e = PaperEngine(MOCK_SPEC)
    e.submit(order())
    e.on_quote(q(2399.0, 2400.0, T0 + timedelta(seconds=1)))  # spread 1.0 > 0.6
    assert e.orders["o1"].status == OrderStatus.REJECTED
    e2 = PaperEngine(MOCK_SPEC)
    e2.submit(order())
    e2.on_quote(q(2399.85, 2400.15, T0 + timedelta(hours=3)))
    assert e2.orders["o1"].status == OrderStatus.EXPIRED
    e3 = PaperEngine(MOCK_SPEC)
    bad = e3.submit(order(stop=2406.0))
    assert bad.status == OrderStatus.REJECTED


def test_limit_and_stop_orders():
    e = PaperEngine(MOCK_SPEC)
    e.submit(order(otype=OrderType.LIMIT, price=2398.0))
    assert not e.on_quote(q(2399.0, 2399.3, T0 + timedelta(seconds=1)))
    pos = e.on_quote(q(2397.5, 2397.8, T0 + timedelta(seconds=2)))
    assert pos and pos[0].entry_price == 2398.0
    e2 = PaperEngine(MOCK_SPEC)
    e2.submit(order(otype=OrderType.STOP, price=2402.0))
    assert not e2.on_quote(q(2400.0, 2400.3, T0 + timedelta(seconds=1)))
    pos = e2.on_quote(q(2402.0, 2402.3, T0 + timedelta(seconds=2)))
    assert pos and pos[0].entry_price == pytest.approx(2402.4)


def test_tp1_partial_then_tp2_and_conservative_same_bar():
    e = PaperEngine(MOCK_SPEC, SlippageParams(0.0, 0.0, 0.0))
    e.submit(order())
    e.on_quote(q(2399.85, 2400.15, T0 + timedelta(seconds=1)))
    pos = e.open_positions()[0]
    e.on_candle(bar(1, 2400, 2405.5, 2399, 2404))  # bid high 2405.35 >= tp1
    assert pos.tp1_hit and pos.lots_open == pytest.approx(0.05) and pos.status == PositionStatus.OPEN
    e.on_candle(bar(2, 2404, 2411, 2403, 2410))
    assert pos.status == PositionStatus.CLOSED and pos.exit_reason == "tp2"
    assert pos.realised_pnl_usd == pytest.approx((2405 - 2400.15) * 0.05 * 100 + (2410 - 2400.15) * 0.05 * 100)
    # same bar stop and tp -> stop first, labelled
    e2 = PaperEngine(MOCK_SPEC, SlippageParams(0.0, 0.0, 0.0))
    e2.submit(order())
    e2.on_quote(q(2399.85, 2400.15, T0 + timedelta(seconds=1)))
    p2 = e2.open_positions()[0]
    e2.on_candle(bar(1, 2400, 2412, 2394, 2411))
    assert p2.status == PositionStatus.CLOSED and p2.exit_reason == "stop" and "CONSERVATIVE_SAME_BAR" in p2.fills[-1].label


def test_gap_through_stop_fills_at_open_with_extra_slippage():
    e = PaperEngine(MOCK_SPEC, SlippageParams(0.0, 0.1, 0.15))
    e.submit(order())
    e.on_quote(q(2399.85, 2400.15, T0 + timedelta(seconds=1)))
    p = e.open_positions()[0]
    e.on_candle(bar(1, 2390.0, 2391.0, 2389.0, 2390.5))  # opens below stop
    assert p.status == PositionStatus.CLOSED
    assert "GAP_THROUGH_STOP" in p.fills[-1].label
    assert p.fills[-1].price == pytest.approx(2390.0 - 0.15 - 0.25)  # open bid minus slippage(0.1+0.15)


def test_time_stop_friday_close_and_partial_fills():
    e = PaperEngine(MOCK_SPEC, max_fill_lots=0.05)
    e.submit(order(lots=0.1))
    p1 = e.on_quote(q(2399.85, 2400.15, T0 + timedelta(seconds=1)))
    assert e.orders["o1"].status == OrderStatus.PARTIAL and p1[0].lots_initial == 0.05
    e.on_quote(q(2399.85, 2400.15, T0 + timedelta(seconds=2)))
    assert e.orders["o1"].status == OrderStatus.FILLED and len(e.open_positions()) == 2
    # time stop after max holding
    e.on_candle(bar(8 * 60 + 1, 2401, 2401.5, 2400.5, 2401))
    assert all(p.status == PositionStatus.CLOSED and p.exit_reason == "time_stop" for p in e.positions.values())
    e3 = PaperEngine(MOCK_SPEC)
    e3.submit(order())
    e3.on_quote(q(2399.85, 2400.15, T0 + timedelta(seconds=1)))
    closed = e3.close_all(q(2402.0, 2402.3, T0 + timedelta(minutes=5)), "friday_close")
    assert len(closed) == 1 and e3.positions[closed[0]].exit_reason == "friday_close"


def test_out_of_order_time_rejected_and_stop_never_widened():
    e = PaperEngine(MOCK_SPEC)
    e.submit(order())
    e.on_quote(q(2399.85, 2400.15, T0 + timedelta(seconds=5)))
    with pytest.raises(ValueError):
        e.on_quote(q(2399.85, 2400.15, T0 + timedelta(seconds=1)))
    p = e.open_positions()[0]
    assert p.stop == p.initial_stop and not hasattr(e, "widen_stop")
