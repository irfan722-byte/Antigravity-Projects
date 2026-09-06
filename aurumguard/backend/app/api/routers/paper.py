from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ...core.contract_spec import get_spec
from ...core.setup import Decision, DecisionStatus, Target, TradeSetup
from ...db.base import get_db
from ...db.models import DecisionRecord, User
from ...providers.base import ProviderError
from ...services import audit
from ...services.analysis import _limits
from ...services.paper_service import PaperService
from ..deps import current_user
from ..schemas import PaperCloseIn, PaperOrderIn

router = APIRouter(prefix="/paper", tags=["paper"])
UTC = UTC


def _decision_from_record(r: DecisionRecord) -> Decision:
    s = dict(r.setup or {})
    for k in ("price_timestamp", "expiry", "max_holding_until", "notification_timestamp"):
        if s.get(k):
            s[k] = datetime.fromisoformat(s[k])
    s["targets"] = [Target(**t) for t in s.get("targets", [])]
    setup = TradeSetup(**s)
    return Decision(r.id, DecisionStatus(r.status), r.horizon, r.strategy_id, r.strategy_version, r.as_of.replace(tzinfo=UTC), r.reason, setup, r.evidence, r.score, r.regime, r.demo_data)


@router.get("/positions")
def positions(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    spec = get_spec(user.settings.contract_spec_id)
    paper = PaperService(db, spec)
    eng = paper.load_engine(user.id)
    ps = request.app.state.providers
    unreal = None
    try:
        q = ps.market.get_quote("XAUUSD", datetime.now(tz=UTC))
        unreal = round(eng.unrealised(q), 2)
    except ProviderError:
        pass
    return {"open": [paper.position_dict(p) for p in eng.open_positions()], "closed": [paper.position_dict(p) for p in eng.positions.values() if p.status.value == "CLOSED"][-100:], "pending_orders": [{"order_id": o.order_id, "decision_id": o.decision_id, "direction": o.direction, "lots": o.lots, "status": o.status.value, "expiry": o.expiry, "reject_reason": o.reject_reason} for o in eng.orders.values() if o.status.value in ("PENDING", "PARTIAL", "REJECTED")][-50:], "realised_usd": round(eng.realised(), 2), "unrealised_usd": unreal, "open_risk_usd": round(eng.open_risk_usd(), 2), "demo_data": ps.demo_mode}


@router.post("/orders", status_code=201)
def place_order(body: PaperOrderIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    request.app.state.limiter.check(request, "paper_order", 30)
    r = db.get(DecisionRecord, body.decision_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, "decision not found")
    if r.status not in ("BUY_SETUP", "SELL_SETUP") or not r.setup:
        raise HTTPException(400, "decision is not an actionable setup")
    limits = _limits(user.settings)
    spec = get_spec(user.settings.contract_spec_id)
    paper = PaperService(db, spec)
    eng = paper.load_engine(user.id)
    now = datetime.now(tz=UTC)
    equity = limits.account_equity if limits.account_currency == "USD" else limits.account_equity / request.app.state.settings.usd_aed_rate
    account = paper.account_state(user.id, eng, equity, now)
    try:
        order = paper.place_from_decision(user.id, eng, _decision_from_record(r), limits, account, now, user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    ps = request.app.state.providers
    try:
        paper.step(user.id, eng, [], ps.market.get_quote("XAUUSD", now))
    except ProviderError:
        paper.persist(user.id, eng)
    o = eng.orders[order.order_id]
    return {"order_id": o.order_id, "status": o.status.value, "reject_reason": o.reject_reason, "lots": o.lots, "risk_usd": round(o.risk_usd, 2), "positions": [paper.position_dict(p) for p in eng.positions.values() if p.order_id == o.order_id]}


@router.post("/close")
def close(body: PaperCloseIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    spec = get_spec(user.settings.contract_spec_id)
    paper = PaperService(db, spec)
    eng = paper.load_engine(user.id)
    if body.position_id not in eng.positions:
        raise HTTPException(404, "position not found")
    ps = request.app.state.providers
    try:
        q = ps.market.get_quote("XAUUSD", datetime.now(tz=UTC))
    except ProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    eng.close_position(body.position_id, q, "manual", body.reason)
    paper.persist(user.id, eng)
    audit.record(db, user.id, "paper.manual_close", body.position_id, {"reason": body.reason})
    return paper.position_dict(eng.positions[body.position_id])


@router.get("/journal")
def journal(user: User = Depends(current_user), db: Session = Depends(get_db)):
    paper = PaperService(db, get_spec(user.settings.contract_spec_id))
    return {"trades": paper.journal(user.id), "events": paper.events(user.id)}


@router.get("/performance")
def performance(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    limits = _limits(user.settings)
    equity = limits.account_equity if limits.account_currency == "USD" else limits.account_equity / request.app.state.settings.usd_aed_rate
    paper = PaperService(db, get_spec(user.settings.contract_spec_id))
    return paper.performance(user.id, equity) | {"label_note": "PAPER results only; never combined with backtest figures", "demo_data": request.app.state.providers.demo_mode}


@router.get("/export.csv")
def export_csv(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from fastapi.responses import PlainTextResponse

    paper = PaperService(db, get_spec(user.settings.contract_spec_id))
    rows = paper.journal(user.id)
    if not rows:
        return PlainTextResponse("trade_id\n", media_type="text/csv")
    cols = list(rows[0].keys())
    lines = [",".join(cols)] + [",".join(str(r.get(c, "")).replace(",", ";") for c in cols) for r in rows]
    return PlainTextResponse("\n".join(lines), media_type="text/csv")
