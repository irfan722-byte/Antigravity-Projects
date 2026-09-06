"""Builds a MarketSnapshot from the configured providers for a given evaluation time.

Point-in-time discipline: every fetch is bounded by ``now``; candles are cut to
closed bars only; calendar and macro data are requested "as of" now so that a
backtest replay through this same function cannot see the future.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta

import numpy as np

from ..core.candles import Candle, Timeframe, only_complete
from ..core.decision import MarketSnapshot
from ..core.evidence import Evidence, Family
from ..core.integrity import IntegrityConfig, IntegrityReport, validate_candles, validate_quote
from ..core.news_state import NewsConfig, assess_news_state
from ..core.regime import IntermarketInputs
from ..core.timeutil import ensure_utc, market_state, session_label
from ..providers.base import ProviderError
from ..providers.registry import ProviderSet

LOOKBACK_BARS = {
    Timeframe.M1: 600,
    Timeframe.M5: 600,
    Timeframe.M15: 500,
    Timeframe.H1: 400,
    Timeframe.H4: 300,
    Timeframe.D1: 260,
    Timeframe.W1: 60,
}
DEFAULT_TFS = [Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1]


def _lookback(tf: Timeframe) -> timedelta:
    bars = LOOKBACK_BARS[tf]
    # market is open ~5/7 of the week; add slack for weekends and holidays
    return timedelta(seconds=bars * tf.seconds * 7 / 5) + timedelta(days=3)


def _zscore_change(series: list[float], horizon: int = 5, window: int = 60, additive: bool = False) -> tuple[float | None, float | None]:
    if len(series) < horizon + window + 1:
        return None, None
    arr = np.asarray(series, dtype=float)
    ch = (arr[horizon:] - arr[:-horizon]) if additive else (arr[horizon:] / arr[:-horizon] - 1)
    hist = ch[-window - 1 : -1]
    cur = float(ch[-1])
    sd = float(hist.std(ddof=1)) if len(hist) > 2 else 0.0
    return cur, (cur / sd if sd > 0 else None)


def build_snapshot(providers: ProviderSet, now: datetime, user_tz: str, timeframes: list[Timeframe] | None = None, integrity: IntegrityConfig | None = None, news_cfg: NewsConfig | None = None) -> MarketSnapshot:
    now = ensure_utc(now)
    icfg = integrity or IntegrityConfig()
    tfs = timeframes or DEFAULT_TFS
    data_unavailable: list[str] = []
    sources: dict[str, str] = {}
    market = providers.market
    demo = providers.demo_mode

    # calendar state
    cal_ok = providers.trading_calendar.verified()
    holidays = providers.trading_calendar.holidays(now.year) | providers.trading_calendar.holidays(now.year + 1)
    early = providers.trading_calendar.early_closes_ny(now.year)
    mstate = market_state(now, holidays, early)
    sources["trading_calendar"] = providers.trading_calendar.name

    # quote
    quote = None
    quote_report: IntegrityReport | None = None
    try:
        quote = market.get_quote("XAUUSD", now)
        quote_report = validate_quote(quote, now, icfg)
    except ProviderError as exc:
        data_unavailable.append(f"quote: {exc}")

    # candles
    candles: dict[Timeframe, list[Candle]] = {}
    reports: dict[Timeframe, IntegrityReport] = {}
    for tf in tfs:
        try:
            raw = market.get_candles("XAUUSD", tf, now - _lookback(tf), now)
        except ProviderError as exc:
            data_unavailable.append(f"{tf.value} candles: {exc}")
            continue
        closed = only_complete(raw, now)
        candles[tf] = closed
        reports[tf] = validate_candles(closed, tf, now, icfg, holidays)
    sources["market_data"] = market.name

    # spread stats
    median_spread = market.median_spread("XAUUSD", now)
    if median_spread is None and candles.get(Timeframe.M5):
        sp = [c.spread_close for c in candles[Timeframe.M5][-200:] if c.spread_close is not None]
        median_spread = statistics.median(sp) if sp else None

    # macro / intermarket (daily, as-of now)
    macro = providers.macro
    series: dict[str, list[float]] = {}
    series_ts: dict[str, list[datetime]] = {}
    try:
        for sid in ("DXY", "US10Y", "US2Y", "REAL10Y", "BREAKEVEN10Y", "EQUITY_INDEX", "VOL_INDEX"):
            pts = macro.get_series(sid, now - timedelta(days=400), now, now)
            series[sid] = [p.value for p in pts]
            series_ts[sid] = [p.ts for p in pts]
        sources["macro_series"] = macro.name
    except ProviderError as exc:
        data_unavailable.append(f"macro series: {exc}")

    inter_ev: list[Evidence] = []
    macro_ev: list[Evidence] = []
    intermarket: IntermarketInputs | None = None
    daily = candles.get(Timeframe.D1) or []
    if series.get("DXY") and daily:
        # align gold daily closes to the DXY dates (by calendar date)
        gold_by_date = {c.ts.date(): c.close for c in daily}
        aligned_gold = []
        aligned = {k: [] for k in series}
        for i, ts in enumerate(series_ts["DXY"]):
            g = gold_by_date.get(ts.date())
            if g is None:
                continue
            aligned_gold.append(g)
            for k in series:
                if i < len(series[k]):
                    aligned[k].append(series[k][i])
        intermarket = IntermarketInputs(gold=aligned_gold, dxy=aligned["DXY"], us10y=aligned["US10Y"], us2y=aligned["US2Y"], real_yield_proxy=aligned["REAL10Y"], risk_index=aligned["EQUITY_INDEX"], vol_index=aligned["VOL_INDEX"], as_of=now)
        label = " (DEMO)" if demo else ""
        ch, z = _zscore_change(series["DXY"])
        if z is not None:
            inter_ev.append(Evidence(Family.INTERMARKET, "dxy", -1 if ch > 0 else 1, min(1.0, abs(z) / 2), f"DXY 5-day change {ch:+.2%} (z={z:+.1f}){label}", f"macro:{macro.name}", now, correlated_group="dollar"))
        ch, z = _zscore_change(series["US10Y"], additive=True)
        if z is not None:
            inter_ev.append(Evidence(Family.INTERMARKET, "us10y", -1 if ch > 0 else 1, min(1.0, abs(z) / 2), f"US10Y 5-day change {ch * 100:+.0f}bp (z={z:+.1f}){label}", f"macro:{macro.name}", now, correlated_group="yields"))
        ch, z = _zscore_change(series["REAL10Y"], additive=True)
        if z is not None:
            inter_ev.append(Evidence(Family.INTERMARKET, "real_yield_proxy", -1 if ch > 0 else 1, min(1.0, abs(z) / 2), f"real-yield proxy 5-day change {ch * 100:+.0f}bp (z={z:+.1f}){label}", f"macro:{macro.name}", now, correlated_group="yields"))
        ch, z = _zscore_change(series["BREAKEVEN10Y"], additive=True)
        if z is not None:
            macro_ev.append(Evidence(Family.MACRO, "inflation_expectations", 1 if ch > 0 else -1, min(1.0, abs(z) / 2), f"10y breakeven 5-day change {ch * 100:+.0f}bp (z={z:+.1f}){label}", f"macro:{macro.name}", now))
        if series.get("US2Y") and series.get("US10Y"):
            curve = series["US10Y"][-1] - series["US2Y"][-1]
            macro_ev.append(Evidence(Family.MACRO, "yield_curve", 0, 0.2, f"2s10s {curve * 100:+.0f}bp{label}", f"macro:{macro.name}", now))
        ch, z = _zscore_change(series["EQUITY_INDEX"])
        vch, vz = _zscore_change(series["VOL_INDEX"])
        if z is not None and vz is not None:
            risk_off = ch < 0 and vch > 0
            risk_on = ch > 0 and vch < 0
            if risk_off or risk_on:
                macro_ev.append(Evidence(Family.MACRO, "risk_sentiment", 1 if risk_off else -1, min(1.0, (abs(z) + abs(vz)) / 4), f"{'risk-off' if risk_off else 'risk-on'}: equities {ch:+.1%}, vol index {vch:+.1%}{label}", f"macro:{macro.name}", now))

    # positioning & ETF flows (slow-moving; labelled as such)
    pos_ev: list[Evidence] = []
    try:
        reps = providers.positioning.get_reports((now - timedelta(days=400)).date(), now.date(), now)
        sources["positioning"] = providers.positioning.name
        if len(reps) >= 26:
            nets = [r.net for r in reps]
            cur = nets[-1]
            pct = sum(1 for x in nets if x < cur) / len(nets) * 100
            if pct >= 90:
                pos_ev.append(Evidence(Family.POSITIONING, "cot_managed_money", -1, 0.4, f"managed-money net long at {pct:.0f}th percentile of 52w (crowded; weekly data as of {reps[-1].report_date}, published {reps[-1].published_ts.date()})", f"cot:{providers.positioning.name}", reps[-1].published_ts))
            elif pct <= 10:
                pos_ev.append(Evidence(Family.POSITIONING, "cot_managed_money", 1, 0.4, f"managed-money net long at {pct:.0f}th percentile of 52w (washed out; weekly data as of {reps[-1].report_date})", f"cot:{providers.positioning.name}", reps[-1].published_ts))
            else:
                pos_ev.append(Evidence(Family.POSITIONING, "cot_managed_money", 0, 0.2, f"managed-money net long at {pct:.0f}th percentile of 52w (weekly, not real-time)", f"cot:{providers.positioning.name}", reps[-1].published_ts))
    except ProviderError as exc:
        data_unavailable.append(f"positioning: {exc}")
    try:
        flows = providers.etf.get_flows((now - timedelta(days=30)).date(), now.date(), now)
        sources["etf_flows"] = providers.etf.name
        if len(flows) >= 5:
            s5 = sum(f.net_flow_tonnes for f in flows[-5:])
            pos_ev.append(Evidence(Family.POSITIONING, "etf_flows_5d", 1 if s5 > 0 else (-1 if s5 < 0 else 0), min(1.0, abs(s5) / 30), f"public ETF net flow last 5 days {s5:+.1f}t (published with a one-day lag)", f"etf:{providers.etf.name}", flows[-1].published_ts))
    except ProviderError as exc:
        data_unavailable.append(f"etf flows: {exc}")

    # economic calendar & news state
    events = []
    try:
        events = providers.calendar.get_events(now - timedelta(days=3), now + timedelta(days=10), now)
        sources["economic_calendar"] = providers.calendar.name
    except ProviderError as exc:
        data_unavailable.append(f"calendar: {exc}")
    reaction_inputs: dict = {}
    m5 = candles.get(Timeframe.M5) or []
    past = [e for e in events if e.scheduled_ts <= now]
    if past and m5:
        ev = past[-1]
        post = [c for c in m5 if c.ts >= ev.scheduled_ts]
        pre = [c for c in m5 if c.ts < ev.scheduled_ts]
        if post and pre:
            move = post[-1].close - pre[-1].close
            reaction_inputs["gold_move_since_release"] = round(move, 2)
            reaction_inputs["gold_response_sign"] = 1 if move > 0 else (-1 if move < 0 else 0)
        if series.get("DXY") and len(series["DXY"]) >= 2:
            d = series["DXY"][-1] - series["DXY"][-2]
            reaction_inputs["dxy_response_sign"] = 1 if d > 0 else (-1 if d < 0 else 0)
            reaction_inputs["dxy_response_basis"] = "daily close change (intraday DXY not available from this provider)"
        if series.get("US10Y") and len(series["US10Y"]) >= 2:
            d = series["US10Y"][-1] - series["US10Y"][-2]
            reaction_inputs["us10y_response_sign"] = 1 if d > 0 else (-1 if d < 0 else 0)
        reaction_inputs["spread_now"] = quote.spread if quote else None
    news = assess_news_state(events, now, news_cfg or NewsConfig(), quote.spread if quote else None, median_spread, reaction_inputs, providers.calendar.reaction_history())

    ok, reason = providers.health_ok()
    return MarketSnapshot(
        as_of=now,
        provider=market.name,
        demo_data=demo,
        quote=quote,
        quote_report=quote_report,
        candles=candles,
        candle_reports=reports,
        news=news,
        session_label=session_label(now),
        market_state=mstate,
        calendar_verified=cal_ok,
        provider_health_ok=ok,
        provider_health_reason=reason,
        median_spread=median_spread,
        intermarket=intermarket,
        intermarket_evidence=inter_ev,
        macro_evidence=macro_ev,
        positioning_evidence=pos_ev,
        data_sources=sources,
        data_unavailable=data_unavailable,
        reaction_inputs=reaction_inputs,
    )
