from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ...backtest.engine import BacktestConfig, Backtester
from ...backtest.validation import run_validation
from ...core.contract_spec import get_spec
from ...core.strategies import build_strategies
from ...db.base import SessionLocal, get_db
from ...db.models import BacktestRun, User
from ...services import audit, strategy_service
from ...services.paper_service import PaperService
from ..deps import admin_user, current_user
from ..schemas import BacktestIn, StrategyActionIn

router = APIRouter(tags=["strategies"])
UTC = UTC


@router.get("/strategies")
def list_strategies(user: User = Depends(current_user), db: Session = Depends(get_db)):
    strategy_service.ensure_records(db)
    return {"strategies": strategy_service.merged_definitions(db), "note": "Only APPROVED strategies can issue setups. Approval requires recorded validation and a human decision."}


@router.get("/strategies/{sid}")
def get_strategy(sid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    for s in strategy_service.merged_definitions(db):
        if s["id"] == sid:
            return s
    raise HTTPException(404, "unknown strategy")


@router.post("/strategies/{sid}/action")
def strategy_action(sid: str, body: StrategyActionIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    try:
        if body.action == "approve":
            rec = strategy_service.approve(db, sid, admin.id, body.note, body.threshold)
        elif body.action == "suspend":
            rec = strategy_service.suspend(db, sid, admin.id, body.note or "manual suspension")
        elif body.action == "reactivate":
            rec = strategy_service.reactivate(db, sid, admin.id, body.note)
        elif body.action == "retire":
            rec = strategy_service.retire(db, sid, admin.id, body.note or "retired")
        else:
            run = db.get(BacktestRun, body.run_id or "")
            if run is None or run.kind != "validation" or run.status != "DONE":
                raise ValueError("record_validation needs a finished validation run id")
            rec = strategy_service.record_validation(db, sid, run.result, admin.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"id": rec.id, "status": rec.status, "production_threshold": rec.production_threshold, "approval_history": rec.approval_history}


def _run_job(run_id: str, body: BacktestIn) -> None:
    db = SessionLocal()
    try:
        run = db.get(BacktestRun, run_id)
        run.status = "RUNNING"
        run.started_at = datetime.now(tz=UTC)
        db.commit()
        from ...config import get_settings
        from ...providers.registry import build_providers

        ps = build_providers(get_settings())
        bt = Backtester(ps.market, ps.calendar, get_spec("mock-generic-100oz"))
        strat = build_strategies()[body.strategy_id]
        start, end = datetime.fromisoformat(body.start).astimezone(UTC), datetime.fromisoformat(body.end).astimezone(UTC)
        data_label = "DEMO" if ps.demo_mode else ps.market.name.upper()
        if body.kind == "validation":
            result = run_validation(bt, strat, start, end, data_label=data_label)
            run.trades_hash = result.get("full_run_hash", "")
        else:
            res = bt.run(strat, BacktestConfig(body.strategy_id, start, end, spread_multiplier=body.spread_multiplier, slippage_multiplier=body.slippage_multiplier, params_override=body.params_override, label="BACKTEST", data_label=data_label))
            result = res.to_dict()
            run.trades_hash = res.trades_hash
            run.config_hash = res.config_hash
        run.result = result
        run.status = "DONE"
        run.finished_at = datetime.now(tz=UTC)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        run = db.get(BacktestRun, run_id)
        if run:
            run.status = "FAILED"
            run.error = str(exc)[:2000]
            run.finished_at = datetime.now(tz=UTC)
            db.commit()
    finally:
        db.close()


@router.post("/backtests", status_code=202)
def start_backtest(body: BacktestIn, tasks: BackgroundTasks, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    request.app.state.limiter.check(request, "backtest", 6)
    if body.strategy_id not in build_strategies():
        raise HTTPException(404, "unknown strategy")
    try:
        start, end = datetime.fromisoformat(body.start), datetime.fromisoformat(body.end)
    except ValueError as exc:
        raise HTTPException(400, "start/end must be ISO timestamps") from exc
    if end <= start or (end - start).days > 400:
        raise HTTPException(400, "window must be positive and at most 400 days")
    strat = build_strategies()[body.strategy_id]
    run = BacktestRun(id=uuid.uuid4().hex[:24], strategy_id=body.strategy_id, strategy_version=strat.definition.version, kind=body.kind, label=body.kind.upper(), data_label="DEMO" if request.app.state.providers.demo_mode else "LIVE", config_hash="", requested_by=user.id)
    db.add(run)
    db.commit()
    audit.record(db, user.id, f"backtest.{body.kind}_requested", run.id, body.model_dump())
    tasks.add_task(_run_job, run.id, body)
    return {"run_id": run.id, "status": run.status}


@router.get("/backtests")
def list_backtests(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(BacktestRun).order_by(desc(BacktestRun.started_at.isnot(None)), desc(BacktestRun.started_at)).limit(50).all()
    return {"runs": [{"run_id": r.id, "strategy_id": r.strategy_id, "strategy_version": r.strategy_version, "kind": r.kind, "label": r.label, "data_label": r.data_label, "status": r.status, "started_at": r.started_at, "finished_at": r.finished_at, "trades_hash": r.trades_hash, "config_hash": r.config_hash, "error": r.error, "summary": {k: r.result.get(k) for k in ("proposed_threshold", "acceptance_checklist")} if r.kind == "validation" else {k: (r.result.get("metrics") or {}).get(k) for k in ("trades", "expectancy_r", "win_rate", "max_drawdown_usd", "profit_factor")}} for r in rows]}


@router.get("/backtests/{run_id}")
def get_backtest(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(BacktestRun, run_id)
    if r is None:
        raise HTTPException(404, "run not found")
    return {"run_id": r.id, "strategy_id": r.strategy_id, "kind": r.kind, "status": r.status, "data_label": r.data_label, "result": r.result, "error": r.error, "trades_hash": r.trades_hash, "config_hash": r.config_hash}


@router.get("/performance/strategies")
def strategy_performance(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Separated samples: validation (from recorded backtests) vs paper (this user)."""
    paper = PaperService(db, get_spec(user.settings.contract_spec_id))
    from ...services.analysis import _limits

    limits = _limits(user.settings)
    equity = limits.account_equity if limits.account_currency == "USD" else limits.account_equity / request.app.state.settings.usd_aed_rate
    paper_perf = paper.performance(user.id, equity)
    out = []
    for s in strategy_service.merged_definitions(db):
        val = s.get("validation_results") or {}
        bt = s.get("backtest_results") or {}
        out.append({"id": s["id"], "name": s["name"], "version": s["version"], "status": s["status"], "horizon": s["horizon"], "production_threshold": s.get("production_threshold"), "validation": {"label": val.get("label"), "data_label": val.get("data_label"), "sample_size": val.get("sample_size"), "wins": val.get("wins"), "expectancy_r": val.get("expectancy_r"), "buckets": val.get("buckets"), "validated_at": val.get("validated_at")}, "in_sample": {k: (bt.get("in_sample") or {}).get(k) for k in ("trades", "expectancy_r", "win_rate", "max_drawdown_r", "profit_factor")}, "out_of_sample": {k: (bt.get("out_of_sample") or {}).get(k) for k in ("trades", "expectancy_r", "win_rate", "max_drawdown_r", "profit_factor", "expectancy_r_ci95_bootstrap", "brier", "calibration_buckets")}, "paper": (paper_perf.get("by_strategy") or {}).get(s["id"], {"trades": 0}), "rolling_paper": s.get("paper_results") or {}})
    return {"strategies": out, "demo_data": request.app.state.providers.demo_mode, "note": "In-sample, out-of-sample and paper samples are reported separately and never combined."}
