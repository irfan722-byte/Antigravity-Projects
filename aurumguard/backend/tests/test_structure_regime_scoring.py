from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.core.candles import Candle, Timeframe, resample
from app.core.evidence import Evidence, Family, score_evidence
from app.core.gates import GateContext, all_passed, evaluate_gates, failed_codes
from app.core.integrity import DataStatus
from app.core.regime import IntermarketInputs, Regime, classify_regime
from app.core.structure import (
    Level,
    StructureParams,
    SwingKind,
    Trend,
    analyse_structure,
    break_of_structure,
    classify_trend,
    detect_failed_breakout,
    detect_sweep,
    find_swings,
    previous_period_levels,
)
from app.providers.mock.synth import minute_path

UTC = UTC


def mk(i, o, h, l, c, start=datetime(2026, 3, 10, 8, 0, tzinfo=UTC), tf=Timeframe.M15):
    ts = start + i * tf.delta
    return Candle("XAUUSD", tf, ts, o, h, l, c, provider="t", ingested_at=ts + tf.delta)


def zigzag(prices, start=datetime(2026, 3, 10, 8, 0, tzinfo=UTC)):
    out = []
    for i, p in enumerate(prices):
        out.append(mk(i, p, p + 0.4, p - 0.4, p + 0.1, start))
    return out


def test_structure_params_range_validation():
    with pytest.raises(ValueError):
        StructureParams(swing_left=1)
    with pytest.raises(ValueError):
        StructureParams(displacement_atr_mult=5.0)


def test_swings_and_trend_up():
    # Higher highs / higher lows
    prices = [100, 101, 102, 103, 104, 103, 102, 101, 102, 103, 104, 105, 106, 105, 104, 103, 104, 105, 106, 107, 108, 107, 106, 105, 106, 107]
    cs = zigzag(prices)
    sw = find_swings(cs, StructureParams(swing_left=3, swing_right=3))
    highs = [s for s in sw if s.kind == SwingKind.HIGH]
    lows = [s for s in sw if s.kind == SwingKind.LOW]
    assert len(highs) >= 2 and len(lows) >= 2
    assert classify_trend(sw) == Trend.UP
    down = zigzag(list(reversed(prices)))
    assert classify_trend(find_swings(down)) == Trend.DOWN


def test_swing_confirmation_needs_right_bars():
    prices = [100, 101, 102, 103, 104, 103, 102]
    cs = zigzag(prices)
    sw = find_swings(cs, StructureParams(swing_left=3, swing_right=3))
    # the peak at index 4 needs bars 5,6,7 to confirm; only 5,6 exist -> not yet a swing
    assert not any(s.kind == SwingKind.HIGH and s.index == 4 for s in sw)


def test_break_of_structure_bullish():
    prices = [100, 101, 102, 103, 104, 103, 102, 101, 100, 101, 102, 103, 104, 103, 102, 101, 100, 101, 102, 103, 104, 105, 106, 107]
    cs = zigzag(prices)
    cs[-1] = mk(len(cs) - 1, 106, 108.5, 105.8, 108.2)
    sw = find_swings(cs)
    ev = break_of_structure(cs, sw)
    assert ev is not None and ev.direction == "bullish" and ev.kind in ("BOS", "MSS")


def test_failed_breakout_and_sweep():
    base = [100.0] * 30
    cs = zigzag(base)
    lvl = Level("PDH", 100.5, "resistance", "PDH")
    # break above then close back below within 3 bars
    cs[-3] = mk(len(cs) - 3, 100.2, 101.5, 100.1, 101.3)
    cs[-2] = mk(len(cs) - 2, 101.3, 101.6, 100.6, 100.8)
    cs[-1] = mk(len(cs) - 1, 100.8, 100.9, 99.9, 100.0)
    ev = detect_failed_breakout(cs, lvl)
    assert ev is not None and ev.kind == "FAILED_BREAKOUT" and ev.label == "Possible failed breakout"
    # sweep: wick above level, close back inside on same bar
    cs2 = zigzag(base)
    cs2[-1] = mk(len(cs2) - 1, 100.2, 101.4, 100.0, 100.1)
    sw = detect_sweep(cs2, lvl)
    assert sw is not None and sw.kind == "SWEEP_HIGH" and sw.label == "Possible stop-run-like behaviour"


def test_previous_day_levels_exclude_today():
    start = datetime(2026, 3, 9, 10, 0, tzinfo=UTC)
    cs = []
    for d in range(3):
        for i in range(8):
            ts = start + timedelta(days=d, hours=i)
            base = 2400 + d * 10
            cs.append(Candle("XAUUSD", Timeframe.H1, ts, base, base + i + 1, base - 1, base + i, provider="t", ingested_at=ts + timedelta(hours=1)))
    as_of = start + timedelta(days=2, hours=5)
    lv = {l.name: l.price for l in previous_period_levels(cs, as_of)}
    assert lv["PDH"] == 2410 + 8 and lv["PDL"] == 2409
    # previous week levels not available: all three days in same ISO week
    assert "PWH" not in lv


def test_analyse_structure_on_synthetic_data():
    start = datetime(2026, 3, 2, 0, 0, tzinfo=UTC)
    m1 = minute_path(start, start + timedelta(days=5))
    m15 = resample(m1, Timeframe.M15)
    as_of = m15[-1].end_ts
    snap = analyse_structure(m15, as_of)
    assert snap.atr and snap.atr > 0
    assert snap.trend in Trend
    names = {l.name for l in snap.levels}
    assert "PDH" in names and "PDL" in names
    d = snap.to_dict()
    assert d["timeframe"] == "M15"


def test_regime_unknown_with_few_bars_and_strong_trend_detection():
    start = datetime(2026, 2, 2, 0, 0, tzinfo=UTC)
    m1 = minute_path(start, start + timedelta(days=3))
    h4 = resample(m1, Timeframe.H4)
    r = classify_regime(h4, None, None, None, "NONE", "LONDON", 0.3, 0.3, h4[-1].end_ts)
    assert r.primary == Regime.UNKNOWN and r.confidence == 0.0
    # synthetic strong uptrend
    cs = []
    for i in range(120):
        ts = start + i * Timeframe.H4.delta
        p = 2300 + i * 3 + (i % 4)
        cs.append(Candle("XAUUSD", Timeframe.H4, ts, p, p + 4, p - 2, p + 2.5, provider="t", ingested_at=ts + Timeframe.H4.delta))
    snap = analyse_structure(cs, cs[-1].end_ts)
    r2 = classify_regime(cs, snap, None, None, "NONE", "LONDON", 0.3, 0.3, cs[-1].end_ts)
    assert r2.primary in (Regime.STRONG_TREND, Regime.WEAK_TREND)
    assert r2.trend_direction == "UP"
    assert r2.confidence > 0.5


def test_regime_news_and_dollar_tags():
    start = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    cs = []
    for i in range(120):
        ts = start + i * Timeframe.H4.delta
        p = 2300 + (i % 10)
        cs.append(Candle("XAUUSD", Timeframe.H4, ts, p, p + 3, p - 3, p + 1, provider="t", ingested_at=ts + Timeframe.H4.delta))
    gold = [2300 - i * 2 - (1.5 if i % 2 else 0) for i in range(40)]
    dxy = [100 + i * 0.2 + (0.08 if i % 2 else 0) for i in range(40)]
    im = IntermarketInputs(gold=gold, dxy=dxy)
    r = classify_regime(cs, None, None, im, "RELEASE_LOCKOUT", "OFF_HOURS", 1.2, 0.3, cs[-1].end_ts)
    assert Regime.NEWS_DOMINATED in r.tags
    assert Regime.THIN_LIQUIDITY in r.tags
    assert Regime.DOLLAR_DRIVEN in r.tags
    assert r.measurements["corr_gold_dxy"] < -0.5


def test_scoring_collapses_correlated_and_requires_independence():
    items = [
        Evidence(Family.TECHNICAL, "rsi", 1, 0.9, "rsi", "t"),
        Evidence(Family.TECHNICAL, "stochastic", 1, 0.8, "stoch", "t"),
        Evidence(Family.TECHNICAL, "ema_fast_slow", 1, 0.6, "ema", "t"),
        Evidence(Family.STRUCTURE, "bos", 1, 0.7, "bos", "t"),
        Evidence(Family.MACRO, "real_yield", -1, 0.5, "yields up", "t"),
    ]
    b = score_evidence(items, +1)
    tech = next(f for f in b.families if f.family == Family.TECHNICAL)
    assert "stochastic" in [e.key for e in tech.items_collapsed]
    assert 50 < b.score < 100
    assert any(e.key == "real_yield" for e in b.contradicting)
    assert b.independent_families_supporting == 2
    # opposite direction should mirror below 50
    b2 = score_evidence(items, -1)
    assert b2.score < 50
    with pytest.raises(ValueError):
        score_evidence(items, 0)


def test_single_family_domination_is_capped():
    items = [Evidence(Family.TECHNICAL, f"k{i}", 1, 1.0, "x", "t") for i in range(3)]
    b = score_evidence(items, +1)
    assert b.dominant_family_share == 1.0
    assert b.notes and b.score < 60


def _ctx(**over):
    base = dict(
        data_status=DataStatus.VALID,
        data_reasons=[],
        event_ts_verified=True,
        spread=0.3,
        max_spread=0.6,
        expected_slippage=0.1,
        max_slippage=0.3,
        session_label="LONDON",
        allowed_sessions=["LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"],
        news_phase="NONE",
        strategy_status="APPROVED",
        regime_primary="STRONG_TREND",
        regime_tags=[],
        approved_regimes=["STRONG_TREND", "WEAK_TREND"],
        prohibited_regimes=["NEWS_DOMINATED", "THIN_LIQUIDITY", "UNKNOWN"],
        risk_checks={c: (True, "ok") for c in ("G09", "G10", "G11", "G12")},
        net_rr_tp1=1.8,
        min_net_rr=1.5,
        position_size_ok=True,
        position_size_reason="ok",
        econ_conflict_unresolved=False,
        provider_health_ok=True,
        provider_health_reason="ok",
        probability_in_range=True,
        probability_reason="ok",
        calendar_verified=True,
        timezone_verified=True,
        price_confirmation_required=True,
        price_confirmed=True,
    )
    base.update(over)
    return GateContext(**base)


def test_gates_all_pass_and_each_failure_mode():
    assert all_passed(evaluate_gates(_ctx()))
    assert failed_codes(evaluate_gates(_ctx(data_status=DataStatus.INVALID))) == ["G01"]
    assert failed_codes(evaluate_gates(_ctx(spread=0.9))) == ["G03"]
    assert failed_codes(evaluate_gates(_ctx(news_phase="RELEASE_LOCKOUT"))) == ["G06"]
    assert failed_codes(evaluate_gates(_ctx(strategy_status="SUSPENDED"))) == ["G07", "G18"]
    assert failed_codes(evaluate_gates(_ctx(regime_tags=["THIN_LIQUIDITY"]))) == ["G08"]
    assert failed_codes(evaluate_gates(_ctx(regime_primary="UNKNOWN", approved_regimes=[]))) == ["G08"]
    assert failed_codes(evaluate_gates(_ctx(risk_checks={"G09": (True, ""), "G10": (False, "daily loss hit"), "G11": (True, ""), "G12": (True, "")}))) == ["G10"]
    assert failed_codes(evaluate_gates(_ctx(net_rr_tp1=1.2))) == ["G13"]
    assert failed_codes(evaluate_gates(_ctx(position_size_ok=False, position_size_reason="min lot exceeds risk"))) == ["G14"]
    assert failed_codes(evaluate_gates(_ctx(calendar_verified=False))) == ["G19"]
    assert failed_codes(evaluate_gates(_ctx(price_confirmed=False))) == ["G20"]
    assert failed_codes(evaluate_gates(_ctx(price_confirmation_required=False, price_confirmed=False))) == []
    assert failed_codes(evaluate_gates(_ctx(session_label="OFF_HOURS"))) == ["G05"]
    assert failed_codes(evaluate_gates(_ctx(market_open=False))) == ["G05"]
