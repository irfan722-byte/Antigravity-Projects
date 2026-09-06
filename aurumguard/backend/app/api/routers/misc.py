from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ...core.calibration import CALIBRATION_VERSION
from ...core.timeutil import to_user_tz
from ...db.base import get_db
from ...db.models import AnalysisRun, AuditLog, DecisionOutcome, DecisionRecord, NotificationRecord, PushSubscription, StrategyRecord, User
from ...services import audit, strategy_service
from ...services.bus import bus
from ...services.snapshot import build_snapshot
from ..deps import admin_user, current_user
from ..schemas import PushSubscribeIn

router = APIRouter(tags=["misc"])
UTC = UTC


# ------------------------------------------------------------ calendar --
@router.get("/calendar")
def calendar(request: Request, days_back: int = Query(7, le=60), days_ahead: int = Query(14, le=60), user: User = Depends(current_user)):
    ps = request.app.state.providers
    now = datetime.now(tz=UTC)
    events = ps.calendar.get_events(now - timedelta(days=days_back), now + timedelta(days=days_ahead), now)
    return {"events": [e.to_dict(user.settings.timezone) for e in events], "provider": ps.calendar.name, "demo_data": ps.calendar.is_mock, "reaction_history": ps.calendar.reaction_history()}


@router.get("/calendar/{event_id}")
def event_detail(event_id: str, request: Request, user: User = Depends(current_user)):
    ps = request.app.state.providers
    now = datetime.now(tz=UTC)
    events = ps.calendar.get_events(now - timedelta(days=60), now + timedelta(days=60), now)
    ev = next((e for e in events if e.event_id == event_id), None)
    if ev is None:
        raise HTTPException(404, "event not found")
    from ...core.news_state import NewsConfig, _scenarios

    hist = ps.calendar.reaction_history().get(ev.category)
    snap = build_snapshot(ps, now, user.settings.timezone)
    reaction = snap.news.reaction if snap.news.event and snap.news.event.event_id == event_id else None
    return {"event": ev.to_dict(user.settings.timezone), "scenarios": _scenarios(ev, hist), "reaction": reaction, "news_phase": snap.news.phase.value, "config": NewsConfig().__dict__ | {"min_importance": NewsConfig().min_importance.value}, "demo_data": ps.calendar.is_mock}


# ------------------------------------------------------------ regime ---
@router.get("/regime")
def regime(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    latest = db.query(DecisionRecord).filter(DecisionRecord.user_id == user.id, DecisionRecord.horizon == "INTRADAY").order_by(desc(DecisionRecord.as_of)).first()
    reg = (latest.evidence or {}).get("regime") if latest else None
    history = db.query(DecisionRecord.as_of, DecisionRecord.regime).filter(DecisionRecord.user_id == user.id, DecisionRecord.horizon == "INTRADAY", DecisionRecord.regime.isnot(None)).order_by(desc(DecisionRecord.as_of)).limit(200).all()
    last_change = None
    prev = None
    for ts, r in reversed(history):
        if prev is not None and r != prev:
            last_change = {"ts": ts, "from": prev, "to": r}
        prev = r
    strategies = strategy_service.merged_definitions(db)
    allowed, prohibited = [], []
    if reg:
        rs = {reg["primary"], *reg.get("tags", [])}
        for s in strategies:
            if reg["primary"] in s["approved_regimes"] and not (rs & set(s["prohibited_regimes"])):
                allowed.append(s["id"])
            else:
                prohibited.append(s["id"])
    return {"regime": reg, "last_change": last_change, "history": [{"ts": ts, "regime": r} for ts, r in history[:50]], "strategies_allowed": allowed, "strategies_prohibited": prohibited, "as_of": latest.as_of if latest else None}


# ------------------------------------------------------ notifications --
@router.get("/notifications")
def notifications(limit: int = Query(50, le=200), user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(NotificationRecord).filter(NotificationRecord.user_id == user.id).order_by(desc(NotificationRecord.created_at)).limit(limit).all()
    return {"items": [{"id": r.id, "kind": r.kind, "priority": r.priority, "title": r.title, "body": r.body, "payload": r.payload, "created_at": r.created_at, "created_local": to_user_tz(r.created_at.replace(tzinfo=UTC), user.settings.timezone), "delivery_status": r.delivery_status, "delivery_detail": r.delivery_detail, "attempts": r.attempts, "read_at": r.read_at} for r in rows]}


@router.post("/notifications/{nid}/read")
def mark_read(nid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(NotificationRecord, nid)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, "not found")
    r.read_at = datetime.now(tz=UTC)
    db.commit()
    return {"ok": True}


@router.post("/push/subscribe", status_code=201)
def push_subscribe(body: PushSubscribeIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    endpoint = str(body.subscription.get("endpoint", ""))
    if not endpoint.startswith("https://"):
        raise HTTPException(400, "subscription endpoint must be https")
    h = hashlib.sha256(endpoint.encode()).hexdigest()
    rec = db.query(PushSubscription).filter(PushSubscription.endpoint_hash == h).first()
    if rec is None:
        rec = PushSubscription(id=uuid.uuid4().hex[:24], user_id=user.id, endpoint_hash=h, subscription=body.subscription, user_agent=body.user_agent[:255])
        db.add(rec)
    else:
        rec.user_id, rec.subscription, rec.active, rec.failures = user.id, body.subscription, True, 0
    db.commit()
    audit.record(db, user.id, "push.subscribed", rec.id)
    return {"id": rec.id, "active": rec.active, "push_provider": request.app.state.providers.push.name, "vapid_public_key": request.app.state.settings.vapid_public_key}


@router.delete("/push/subscribe", status_code=204)
def push_unsubscribe(user: User = Depends(current_user), db: Session = Depends(get_db)):
    for rec in db.query(PushSubscription).filter(PushSubscription.user_id == user.id).all():
        rec.active = False
    db.commit()


@router.get("/push/vapid-public-key")
def vapid_key(request: Request):
    return {"vapid_public_key": request.app.state.settings.vapid_public_key, "push_provider": request.app.state.settings.push_provider}


# --------------------------------------------------------------- SSE ---
@router.get("/stream")
async def stream(request: Request, user: User = Depends(current_user)):
    q = bus.subscribe(user.id)

    async def gen():
        try:
            yield "event: hello\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {msg}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            bus.unsubscribe(user.id, q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --------------------------------------------------------- calibration --
@router.get("/calibration")
def calibration(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Realised outcomes of issued setups bucketed by score, versus the calibrated range shown at issue time."""
    rows = db.query(DecisionRecord, DecisionOutcome).join(DecisionOutcome, DecisionOutcome.decision_id == DecisionRecord.id).filter(DecisionRecord.user_id == user.id).all()
    buckets: dict[str, dict] = {}
    pairs = []
    for d, o in rows:
        if d.score is None:
            continue
        from ...core.calibration import bucket_for

        b = buckets.setdefault(bucket_for(d.score), {"n": 0, "wins": 0, "predicted_mid": []})
        b["n"] += 1
        win = o.outcome in ("TP1", "TP2")
        b["wins"] += int(win)
        s = d.setup or {}
        mid = (s.get("confidence_low", 0) + s.get("confidence_high", 1)) / 2
        b["predicted_mid"].append(mid)
        pairs.append((mid, int(win)))
    out = []
    for k, b in sorted(buckets.items()):
        out.append({"bucket": k, "n": b["n"], "observed_win_rate": round(b["wins"] / b["n"], 3), "predicted_mid": round(sum(b["predicted_mid"]) / len(b["predicted_mid"]), 3)})
    from ...core.calibration import brier_score

    strategies = {r.id: {"validation_buckets": (r.validation or {}).get("buckets"), "brier_validation": (r.validation or {}).get("brier")} for r in db.query(StrategyRecord).all()}
    return {"version": CALIBRATION_VERSION, "live_outcomes": out, "brier_live": round(brier_score(pairs), 4) if pairs else None, "sample": len(pairs), "strategies": strategies, "note": "Outcomes are evaluated on the mid-price path within each setup's window (no fill simulation). Small samples are not evidence of calibration."}


# --------------------------------------------------------------- audit --
@router.get("/audit")
def audit_log(limit: int = Query(100, le=500), user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(AuditLog)
    if user.role != "admin":
        q = q.filter(AuditLog.actor == user.id)
    rows = q.order_by(desc(AuditLog.id)).limit(limit).all()
    return {"items": [{"id": r.id, "ts": r.ts, "actor": r.actor, "action": r.action, "subject": r.subject, "detail": r.detail, "row_hash": r.row_hash} for r in rows], "chain": audit.verify_chain(db, 500) if user.role == "admin" else None}


# --------------------------------------------------------------- admin --
@router.get("/admin/overview")
def admin_overview(request: Request, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    s = request.app.state.settings
    runs = db.query(AnalysisRun).order_by(desc(AnalysisRun.ts)).limit(10).all()
    return {"environment": s.app_env, "config_problems": s.validate_for_environment(), "providers": {"market": s.market_data_provider, "calendar": s.calendar_provider, "push": s.push_provider}, "demo_data": request.app.state.providers.demo_mode, "users": db.query(User).filter(User.deleted_at.is_(None)).count(), "strategies": [{"id": r.id, "status": r.status, "version": r.version, "threshold": r.production_threshold} for r in db.query(StrategyRecord).all()], "analysis_runs": [{"ts": r.ts, "as_of": r.as_of, "users": r.users, "duration_ms": round(r.duration_ms, 1), "data_status": r.data_status} for r in runs], "scheduler_running": bool(getattr(request.app.state, "scheduler_running", False)), "live_execution": "DISABLED (not implemented in MVP)"}


@router.post("/admin/run-analysis")
def admin_run(request: Request, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    return request.app.state.analysis.run_once(db)
