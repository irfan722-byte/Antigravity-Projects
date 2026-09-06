from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ...core.candles import Timeframe
from ...core.integrity import validate_quote
from ...core.structure import analyse_structure
from ...core.timeutil import market_state, session_label
from ...db.base import get_db
from ...db.models import AnalysisRun, ProviderHealthRecord, User
from ...providers.base import ProviderError
from ...services.snapshot import build_snapshot
from ..deps import current_user

router = APIRouter(prefix="/market", tags=["market"])
UTC = UTC


@router.get("/quote")
def quote(request: Request, user: User = Depends(current_user)):
    ps = request.app.state.providers
    now = datetime.now(tz=UTC)
    try:
        q = ps.market.get_quote("XAUUSD", now)
    except ProviderError as exc:
        raise HTTPException(503, f"quote unavailable: {exc}") from exc
    rep = validate_quote(q, now)
    return {"instrument": "XAU/USD", "bid": q.bid, "ask": q.ask, "mid": round(q.mid, 2), "spread": round(q.spread, 2), "ts": q.ts, "provider": q.provider, "demo_data": ps.demo_mode, "integrity": rep.to_dict(), "market_state": market_state(now).value, "session": session_label(now), "user_timezone": user.settings.timezone}


@router.get("/candles")
def candles(request: Request, timeframe: str = Query("H1"), bars: int = Query(300, ge=10, le=2000), user: User = Depends(current_user)):
    ps = request.app.state.providers
    try:
        tf = Timeframe(timeframe)
    except ValueError as exc:
        raise HTTPException(400, "unknown timeframe") from exc
    now = datetime.now(tz=UTC)
    span = timedelta(seconds=bars * tf.seconds * 7 / 5) + timedelta(days=3)
    try:
        cs = ps.market.get_candles("XAUUSD", tf, now - span, now)[-bars:]
    except ProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"timeframe": tf.value, "demo_data": ps.demo_mode, "provider": ps.market.name, "candles": [{"time": int(c.ts.timestamp()), "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume, "complete": c.complete} for c in cs]}


@router.get("/structure")
def structure(request: Request, timeframe: str = Query("H1"), user: User = Depends(current_user)):
    ps = request.app.state.providers
    tf = Timeframe(timeframe)
    now = datetime.now(tz=UTC)
    cs = [c for c in ps.market.get_candles("XAUUSD", tf, now - timedelta(seconds=400 * tf.seconds * 7 / 5) - timedelta(days=3), now) if c.complete]
    d1 = [c for c in ps.market.get_candles("XAUUSD", Timeframe.D1, now - timedelta(days=120), now) if c.complete]
    if len(cs) < 30:
        raise HTTPException(503, "insufficient candles")
    return analyse_structure(cs, now, daily_candles=d1).to_dict() | {"demo_data": ps.demo_mode}


@router.get("/snapshot")
def snapshot(request: Request, user: User = Depends(current_user)):
    ps = request.app.state.providers
    now = datetime.now(tz=UTC)
    snap = build_snapshot(ps, now, user.settings.timezone)
    return {
        "as_of": snap.as_of,
        "demo_data": snap.demo_data,
        "quote": None if snap.quote is None else {"bid": snap.quote.bid, "ask": snap.quote.ask, "spread": round(snap.quote.spread, 2), "ts": snap.quote.ts},
        "quote_integrity": snap.quote_report.to_dict() if snap.quote_report else None,
        "candle_integrity": {tf.value: r.to_dict() for tf, r in snap.candle_reports.items()},
        "session": snap.session_label,
        "market_state": snap.market_state.value,
        "news": snap.news.to_dict(user.settings.timezone),
        "intermarket_evidence": [e.to_dict() for e in snap.intermarket_evidence],
        "macro_evidence": [e.to_dict() for e in snap.macro_evidence],
        "positioning_evidence": [e.to_dict() for e in snap.positioning_evidence],
        "intermarket_series": None if snap.intermarket is None else {"gold": snap.intermarket.gold[-60:], "dxy": (snap.intermarket.dxy or [])[-60:], "us10y": (snap.intermarket.us10y or [])[-60:], "us2y": (snap.intermarket.us2y or [])[-60:], "real_yield": (snap.intermarket.real_yield_proxy or [])[-60:], "risk_index": (snap.intermarket.risk_index or [])[-60:], "vol_index": (snap.intermarket.vol_index or [])[-60:]},
        "data_sources": snap.data_sources,
        "data_unavailable": snap.data_unavailable,
        "median_spread": snap.median_spread,
        "provider_health_ok": snap.provider_health_ok,
    }


@router.get("/health")
def provider_health(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ps = request.app.state.providers
    runs = db.query(AnalysisRun).order_by(desc(AnalysisRun.ts)).limit(20).all()
    hist = db.query(ProviderHealthRecord).order_by(desc(ProviderHealthRecord.ts)).limit(50).all()
    return {
        "demo_data": ps.demo_mode,
        "providers": [h.to_dict() | {"doc": (p.doc.__dict__ if p.doc else None)} for h, p in zip(ps.health(), (ps.market, ps.calendar, ps.trading_calendar, ps.macro, ps.news, ps.positioning, ps.etf, ps.push))],
        "analysis_runs": [{"ts": r.ts, "as_of": r.as_of, "users": r.users, "duration_ms": round(r.duration_ms, 1), "data_status": r.data_status} for r in runs],
        "history": [{"ts": h.ts, "ok": all(x["ok"] for x in h.payload)} for h in hist],
    }
