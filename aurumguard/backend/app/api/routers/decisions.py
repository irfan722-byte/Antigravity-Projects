from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ...core.contract_spec import get_spec
from ...core.decision import UserContext
from ...core.risk import lock_status
from ...core.setup import Horizon
from ...db.base import get_db
from ...db.models import DecisionOutcome, DecisionRecord, User
from ...services import strategy_service
from ...services.analysis import _limits
from ...services.paper_service import PaperService
from ...services.snapshot import build_snapshot
from ..deps import current_user

router = APIRouter(prefix="/decisions", tags=["decisions"])
UTC = UTC


def _row(r: DecisionRecord, with_evidence: bool = False) -> dict:
    d = {"decision_id": r.id, "horizon": r.horizon, "status": r.status, "strategy_id": r.strategy_id, "strategy_version": r.strategy_version, "as_of": r.as_of, "reason": r.reason, "score": r.score, "regime": r.regime, "demo_data": r.demo_data, "setup": r.setup, "expiry": r.expiry}
    if with_evidence:
        d["evidence_inspector"] = r.evidence
    return d


@router.get("/latest")
def latest(user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = {}
    for h in Horizon:
        r = db.query(DecisionRecord).filter(DecisionRecord.user_id == user.id, DecisionRecord.horizon == h.value).order_by(desc(DecisionRecord.as_of)).first()
        out[h.value] = _row(r) if r else None
    return {"horizons": out, "user_timezone": user.settings.timezone}


@router.get("/feed")
def feed(status: str | None = None, horizon: str | None = None, limit: int = Query(50, le=200), user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(DecisionRecord).filter(DecisionRecord.user_id == user.id)
    if status:
        q = q.filter(DecisionRecord.status == status)
    if horizon:
        q = q.filter(DecisionRecord.horizon == horizon)
    rows = q.order_by(desc(DecisionRecord.as_of)).limit(limit).all()
    return {"items": [_row(r) for r in rows]}


@router.get("/{decision_id}")
def detail(decision_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(DecisionRecord, decision_id)
    if r is None or (r.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "decision not found")
    outcome = db.query(DecisionOutcome).filter(DecisionOutcome.decision_id == r.id).first()
    d = _row(r, with_evidence=True)
    d["outcome"] = None if outcome is None else {"outcome": outcome.outcome, "evaluated_at": outcome.evaluated_at, "mfe": outcome.max_favourable_excursion, "mae": outcome.max_adverse_excursion, "detail": outcome.detail}
    return d


@router.post("/evaluate-now")
def evaluate_now(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """On-demand evaluation (not persisted; the scheduler is the system of record)."""
    request.app.state.limiter.check(request, "evaluate", 20)
    svc = request.app.state.analysis
    now = datetime.now(tz=UTC)
    snap = build_snapshot(svc.providers, now, user.settings.timezone)
    limits = _limits(user.settings)
    spec = get_spec(user.settings.contract_spec_id)
    paper = PaperService(db, spec)
    eng = paper.load_engine(user.id)
    equity = limits.account_equity if limits.account_currency == "USD" else limits.account_equity / svc.settings.usd_aed_rate
    account = paper.account_state(user.id, eng, equity, now)
    decisions = svc.engine.evaluate_all(snap, UserContext(user.id, user.settings.timezone, limits, account, spec), svc.strategies_by_horizon(), strategy_service.runtime_states(db))
    return {"as_of": now, "demo_data": snap.demo_data, "horizons": {h.value: d.to_dict() for h, d in decisions.items()}, "risk_locks": lock_status(limits, account, now), "persisted": False}
