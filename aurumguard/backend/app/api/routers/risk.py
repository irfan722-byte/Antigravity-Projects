from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ...core.contract_spec import SPECS, get_spec
from ...core.risk import CostModel, compute_position_size, lock_status, net_reward_to_risk
from ...db.base import get_db
from ...db.models import User
from ...services.analysis import _limits
from ...services.paper_service import PaperService
from ..deps import current_user
from ..schemas import PositionSizeIn

router = APIRouter(prefix="/risk", tags=["risk"])
UTC = UTC


@router.get("/status")
def status(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    limits = _limits(user.settings)
    spec = get_spec(user.settings.contract_spec_id)
    paper = PaperService(db, spec)
    eng = paper.load_engine(user.id)
    now = datetime.now(tz=UTC)
    equity = limits.account_equity if limits.account_currency == "USD" else limits.account_equity / request.app.state.settings.usd_aed_rate
    acct = paper.account_state(user.id, eng, equity, now)
    return {
        "limits": limits.to_dict(),
        "account": {"equity_usd": round(acct.equity_usd, 2), "starting_equity_usd": round(equity, 2), "realised_today_usd": round(acct.realised_today_usd, 2), "realised_week_usd": round(acct.realised_week_usd, 2), "month_peak_equity_usd": round(acct.month_peak_equity_usd, 2), "aggregate_open_risk_usd": round(acct.aggregate_open_risk_usd, 2), "aggregate_open_risk_pct": round(acct.aggregate_open_risk_usd / acct.equity_usd * 100, 3) if acct.equity_usd else None, "open_positions": len(acct.open_risks), "trades_today": acct.trades_today, "consecutive_losses": acct.consecutive_losses, "open_risks": [r.__dict__ for r in acct.open_risks]},
        "locks": lock_status(limits, acct, now),
        "unrealised_usd": None,
        "contract_spec": spec.to_dict(),
        "as_of": now,
    }


@router.post("/position-size")
def position_size(body: PositionSizeIn, request: Request, user: User = Depends(current_user)):
    limits = _limits(user.settings)
    spec = get_spec(user.settings.contract_spec_id)
    equity = body.equity if body.equity is not None else (limits.account_equity if limits.account_currency == "USD" else limits.account_equity / request.app.state.settings.usd_aed_rate)
    risk_pct = body.risk_pct if body.risk_pct is not None else limits.risk_per_trade_pct
    if risk_pct > limits.risk_per_trade_pct + 1e-9:
        raise HTTPException(400, f"risk {risk_pct}% exceeds your configured per-trade limit {limits.risk_per_trade_pct}%")
    costs = CostModel(body.spread, body.slippage / 2, body.slippage / 2, spec.commission_per_lot_round_trip_usd)
    res = compute_position_size(equity, risk_pct, body.entry, body.stop, body.direction, costs, spec)
    out = res.to_dict()
    out["net_rr_tp1"] = net_reward_to_risk(body.entry, body.stop, body.tp1, body.direction, costs, spec) if body.tp1 else None
    out["net_rr_tp2"] = net_reward_to_risk(body.entry, body.stop, body.tp2, body.direction, costs, spec) if body.tp2 else None
    out["formula"] = "risk budget = equity x risk%; effective adverse distance = |entry - stop| + spread + slippage(entry+exit); risk per lot = distance x contract size + commission; lots = floor(budget / risk per lot, step)"
    out["contract_spec_verified"] = spec.verified
    return out


@router.get("/contract-specs")
def specs(user: User = Depends(current_user)):
    return {"specs": [s.to_dict() for s in SPECS.values()]}
