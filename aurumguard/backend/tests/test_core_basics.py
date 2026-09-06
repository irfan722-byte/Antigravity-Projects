import math
from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from app.core.candles import Candle, Quote, Timeframe, floor_ts, only_complete, resample
from app.core.indicators import adx, atr, bollinger, donchian, ema, rsi, sma
from app.core.integrity import DataStatus, IntegrityConfig, compare_quotes, validate_candles, validate_event_timestamp, validate_quote
from app.core.timeutil import (
    MarketState,
    Session,
    active_sessions,
    ensure_utc,
    friday_cutoff_utc,
    is_dst_transition_day,
    market_state,
    past_friday_cutoff,
    session_label,
    to_user_tz,
)

UTC = UTC


def mk(ts, o, h, l, c, tf=Timeframe.M5, complete=True):
    return Candle("XAUUSD", tf, ts, o, h, l, c, complete=complete, provider="test", ingested_at=ts + tf.delta)


def series(n, start, tf=Timeframe.M5, price=2400.0, step=0.5):
    out = []
    p = price
    for i in range(n):
        o = p
        c = p + step * (1 if i % 3 else -1)
        out.append(mk(start + i * tf.delta, o, max(o, c) + 0.3, min(o, c) - 0.3, c, tf))
        p = c
    return out


# ---------------------------------------------------------------- time ---

def test_ensure_utc_rejects_naive():
    with pytest.raises(ValueError):
        ensure_utc(datetime(2026, 1, 5, 10, 0))


def test_sessions_and_overlap():
    # 2026-03-10 14:00 UTC: London (14:00 GMT) and NY (10:00 EDT) both active; Tokyo 23:00 not.
    ts = datetime(2026, 3, 10, 14, 0, tzinfo=UTC)
    assert set(active_sessions(ts)) == {Session.LONDON, Session.NEW_YORK}
    assert session_label(ts) == "LONDON_NY_OVERLAP"
    ts2 = datetime(2026, 3, 10, 2, 0, tzinfo=UTC)  # 11:00 Tokyo
    assert active_sessions(ts2) == [Session.ASIA]


def test_market_state_weekend_and_maintenance():
    # Saturday
    assert market_state(datetime(2026, 3, 14, 12, 0, tzinfo=UTC)) == MarketState.WEEKEND
    # Friday 17:30 NY (EDT => 21:30 UTC) closed
    assert market_state(datetime(2026, 3, 13, 21, 30, tzinfo=UTC)) == MarketState.WEEKEND
    # Sunday 18:30 NY (22:30 UTC) open
    assert market_state(datetime(2026, 3, 15, 22, 30, tzinfo=UTC)) == MarketState.OPEN
    # Tuesday 17:30 NY maintenance
    assert market_state(datetime(2026, 3, 10, 21, 30, tzinfo=UTC)) == MarketState.MAINTENANCE
    assert market_state(datetime(2026, 3, 10, 14, 0, tzinfo=UTC)) == MarketState.OPEN
    # holiday from calendar provider
    from datetime import date

    assert market_state(datetime(2026, 12, 25, 14, 0, tzinfo=UTC), holiday_dates={date(2026, 12, 25)}) == MarketState.HOLIDAY


def test_dst_transition_detection():
    from datetime import date

    assert is_dst_transition_day(date(2026, 3, 8), ZoneInfo("America/New_York"))
    assert not is_dst_transition_day(date(2026, 3, 9), ZoneInfo("America/New_York"))
    assert not is_dst_transition_day(date(2026, 3, 8), ZoneInfo("Asia/Dubai"))


def test_friday_cutoff_dubai():
    ts = datetime(2026, 3, 11, 9, 0, tzinfo=UTC)  # Wednesday
    cut = friday_cutoff_utc(ts, "Asia/Dubai", "20:00")
    assert cut == datetime(2026, 3, 13, 16, 0, tzinfo=UTC)  # 20:00 GST == 16:00 UTC
    assert not past_friday_cutoff(ts, "Asia/Dubai", "20:00")
    assert past_friday_cutoff(datetime(2026, 3, 13, 16, 1, tzinfo=UTC), "Asia/Dubai", "20:00")
    assert past_friday_cutoff(datetime(2026, 3, 14, 10, 0, tzinfo=UTC), "Asia/Dubai", "20:00")
    assert not past_friday_cutoff(datetime(2026, 3, 16, 10, 0, tzinfo=UTC), "Asia/Dubai", "20:00")
    assert to_user_tz(ts, "Asia/Dubai").hour == 13


# ------------------------------------------------------------- candles ---

def test_only_complete_hides_future_bars():
    start = datetime(2026, 3, 10, 10, 0, tzinfo=UTC)
    cs = series(10, start)
    as_of = start + 5 * Timeframe.M5.delta + timedelta(seconds=30)
    vis = only_complete(cs, as_of)
    assert len(vis) == 5
    assert all(c.end_ts <= as_of for c in vis)


def test_resample_m5_to_m15_marks_partial_incomplete():
    start = datetime(2026, 3, 10, 10, 0, tzinfo=UTC)
    cs = series(7, start)
    out = resample(cs, Timeframe.M15)
    assert len(out) == 3
    assert out[0].complete and out[1].complete and not out[2].complete
    assert out[0].open == cs[0].open and out[0].close == cs[2].close
    assert out[0].high == max(c.high for c in cs[:3])
    with pytest.raises(ValueError):
        resample(cs, Timeframe.M3)


def test_floor_ts_week_anchor_monday():
    ts = datetime(2026, 3, 12, 15, 0, tzinfo=UTC)  # Thursday
    assert floor_ts(ts, Timeframe.W1) == datetime(2026, 3, 9, 0, 0, tzinfo=UTC)
    assert floor_ts(ts, Timeframe.H4) == datetime(2026, 3, 12, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------- indicators ---

def test_sma_ema_basic():
    v = [1, 2, 3, 4, 5, 6]
    s = sma(v, 3)
    assert math.isnan(s[1]) and s[2] == 2 and s[-1] == 5
    e = ema(v, 3)
    assert e[2] == 2 and e[3] == pytest.approx(3.0)


def test_rsi_bounds_and_direction():
    up = list(range(1, 40))
    r = rsi(up, 14)
    assert r[-1] == 100.0
    mixed = [10 + (i % 2) for i in range(40)]
    r2 = rsi(mixed, 14)
    assert 0 < r2[-1] < 100


def test_atr_and_adx_shapes():
    h = [10 + i * 0.1 + 0.5 for i in range(80)]
    l = [10 + i * 0.1 - 0.5 for i in range(80)]
    c = [10 + i * 0.1 for i in range(80)]
    a = atr(h, l, c, 14)
    assert not math.isnan(a[-1]) and a[-1] == pytest.approx(1.0, abs=0.05)
    ax, pdi, mdi = adx(h, l, c, 14)
    assert not math.isnan(ax[-1])
    assert pdi[-1] > mdi[-1]  # steadily rising series
    assert ax[-1] > 20


def test_bollinger_donchian():
    v = [100 + (i % 5) for i in range(40)]
    m, u, lo, bw = bollinger(v, 20)
    assert u[-1] > m[-1] > lo[-1]
    up, dn = donchian([x + 1 for x in v], [x - 1 for x in v], 20)
    assert up[-1] == 105 and dn[-1] == 99


# ----------------------------------------------------------- integrity ---

def test_quote_validation_cases():
    now = datetime(2026, 3, 10, 14, 0, tzinfo=UTC)
    good = Quote("XAUUSD", 2400.0, 2400.3, now, "mock", now)
    assert validate_quote(good, now).status == DataStatus.VALID
    neg = Quote("XAUUSD", 2400.5, 2400.3, now, "mock", now)
    assert "QUOTE_NEGATIVE_SPREAD" in validate_quote(neg, now).codes()
    zero = Quote("XAUUSD", 2400.3, 2400.3, now, "mock", now)
    rep = validate_quote(zero, now)
    assert "QUOTE_ZERO_SPREAD" in rep.codes() and rep.status == DataStatus.DEGRADED
    wide = Quote("XAUUSD", 2400.0, 2405.0, now, "mock", now)
    assert "QUOTE_EXTREME_SPREAD" in validate_quote(wide, now).codes()
    stale = Quote("XAUUSD", 2400.0, 2400.3, now - timedelta(seconds=90), "mock", now)
    assert "QUOTE_STALE" in validate_quote(stale, now).codes()
    fut = Quote("XAUUSD", 2400.0, 2400.3, now + timedelta(minutes=5), "mock", now)
    assert "QUOTE_FUTURE_TS" in validate_quote(fut, now).codes()
    bad = Quote("XAUUSD", -1.0, 2400.3, now, "mock", now)
    assert validate_quote(bad, now).status == DataStatus.INVALID


def test_candle_validation_duplicates_gaps_outliers_stale():
    start = datetime(2026, 3, 10, 10, 0, tzinfo=UTC)
    cs = series(60, start)
    now = cs[-1].end_ts + timedelta(seconds=10)
    assert validate_candles(cs, Timeframe.M5, now).status == DataStatus.VALID
    dup = cs + [cs[-1]]
    assert "CANDLE_DUPLICATE" in validate_candles(dup, Timeframe.M5, now).codes()
    gap = cs[:30] + cs[35:]
    assert "CANDLE_GAP" in validate_candles(gap, Timeframe.M5, now).codes()
    last = cs[-1]
    spike = Candle("XAUUSD", Timeframe.M5, last.ts, last.open, last.open * 1.2, last.low, last.open * 1.19, provider="test", ingested_at=now)
    assert "CANDLE_OUTLIER" in validate_candles(cs[:-1] + [spike], Timeframe.M5, now).codes()
    stale_now = cs[-1].end_ts + timedelta(minutes=30)
    assert "CANDLES_STALE" in validate_candles(cs, Timeframe.M5, stale_now).codes()
    ooo = [cs[1], cs[0]] + cs[2:]
    assert "CANDLE_OUT_OF_ORDER" in validate_candles(ooo, Timeframe.M5, now).codes()
    bad = cs[:-1] + [Candle("XAUUSD", Timeframe.M5, last.ts, last.open, last.low - 1, last.low, last.close, provider="test", ingested_at=now)]
    assert "CANDLE_OHLC_INCONSISTENT" in validate_candles(bad, Timeframe.M5, now).codes()


def test_candle_gap_over_weekend_not_flagged():
    fri = datetime(2026, 3, 13, 20, 0, tzinfo=UTC)  # Friday 16:00 NY
    cs = series(12, fri)  # ends 21:00 UTC (17:00 NY)
    sun = datetime(2026, 3, 15, 22, 0, tzinfo=UTC)  # Sunday 18:00 NY reopen
    cs2 = series(12, sun)
    now = cs2[-1].end_ts + timedelta(seconds=5)
    rep = validate_candles(cs + cs2, Timeframe.M5, now)
    assert "CANDLE_GAP" not in rep.codes()


def test_cross_provider_and_event_ts():
    now = datetime(2026, 3, 10, 14, 0, tzinfo=UTC)
    a = Quote("XAUUSD", 2400.0, 2400.3, now, "p1", now)
    b = Quote("XAUUSD", 2407.0, 2407.3, now, "p2", now)
    assert "XPROV_DISAGREE" in compare_quotes(a, b).codes()
    sched = datetime(2026, 3, 6, 13, 30, tzinfo=UTC)
    rep = validate_event_timestamp(sched, sched - timedelta(minutes=10), sched, now)
    assert "EVENT_PUBLISHED_BEFORE_SCHEDULE" in rep.codes()
    rep2 = validate_event_timestamp(sched, sched + timedelta(minutes=45), sched + timedelta(minutes=46), now)
    assert "EVENT_DELAYED_RELEASE" in rep2.codes() and rep2.status == DataStatus.DEGRADED
