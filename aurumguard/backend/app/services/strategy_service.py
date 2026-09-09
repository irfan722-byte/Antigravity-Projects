"""Strategy registry state, approval workflow and degradation monitoring.

Rules enforced here:
- A strategy can only become APPROVED through `approve()` by an admin, and only
  when a validation payload with at least MIN_SAMPLE recorded trades exists.
- Suspension is automatic on degradation or manual; reactivation requires a
  version change or a re-validation newer than the suspension, plus an admin.
- Every transition is appended to approval_history and the audit log.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..backtest.metrics import TradeRecord
from ..core.decision import StrategyRuntimeState
from ..core.strategies import load_definitions
from ..core.strategies.base import StrategyDefinition
from ..db.models import StrategyRecord
from . import audit

UTC = UTC
MIN_SAMPLE = 30
VALID_STATUSES = {"RESEARCH", "APPROVED", "SUSPENDED", "RETIRED"}


def ensure_records(db: Session) -> dict[str, StrategyDefinition]:
    defs = load_definitions()
    for sid, d in defs.items():
        rec = db.get(StrategyRecord, sid)
        if rec is None:
            db.add(StrategyRecord(id=sid, version=d.version, status="RESEARCH", change_log=d.change_log, approval_history=[]))
        elif rec.version != d.version:
            rec.change_log = (rec.change_log or []) + [{"version": d.version, "date": datetime.now(tz=UTC).date().isoformat(), "change": "code version changed; status reset to RESEARCH pending re-validation"}]
            rec.version = d.version
            rec.status = "RESEARCH"
            rec.production_threshold = None
    db.commit()
    return defs


def runtime_states(db: Session) -> dict[str, StrategyRuntimeState]:
    out: dict[str, StrategyRuntimeState] = {}
    for rec in db.query(StrategyRecord).all():
        out[rec.id] = StrategyRuntimeState(rec.status, rec.validation or {}, rec.production_threshold, rec.suspension_reason, rec.approval_note or "")
    return out


def merged_definitions(db: Session) -> list[dict]:
    defs = load_definitions()
    out = []
    for sid, d in defs.items():
        rec = db.get(StrategyRecord, sid)
        item = d.to_dict()
        if rec:
            item.update({"status": rec.status, "production_threshold": rec.production_threshold, "validation_results": rec.validation or {}, "backtest_results": rec.backtest_results or {}, "paper_results": rec.paper_results or {}, "approval_history": rec.approval_history or [], "change_log": rec.change_log or d.change_log, "suspension_reason": rec.suspension_reason, "approval_note": rec.approval_note})
        out.append(item)
    return out


def _history(rec: StrategyRecord, entry: dict) -> None:
    rec.approval_history = (rec.approval_history or []) + [entry | {"ts": datetime.now(tz=UTC).isoformat()}]


def record_validation(db: Session, sid: str, report: dict, actor: str) -> StrategyRecord:
    rec = db.get(StrategyRecord, sid)
    if rec is None:
        raise ValueError("unknown strategy")
    payload = dict(report.get("calibration_payload") or {})
    payload["validated_at"] = datetime.now(tz=UTC).isoformat()
    payload["proposed_threshold"] = report.get("proposed_threshold")
    payload["acceptance_checklist"] = report.get("acceptance_checklist")
    rec.validation = payload
    rec.backtest_results = {k: v for k, v in report.items() if k not in ("calibration_payload",)}
    _history(rec, {"action": "validation_recorded", "actor": actor, "sample_size": payload.get("sample_size"), "data_label": payload.get("data_label")})
    db.commit()
    audit.record(db, actor, "strategy.validation_recorded", sid, {"sample_size": payload.get("sample_size"), "data_label": payload.get("data_label"), "proposed_threshold": payload.get("proposed_threshold")})
    return rec


def approve(db: Session, sid: str, actor: str, note: str, threshold: float | None = None) -> StrategyRecord:
    rec = db.get(StrategyRecord, sid)
    if rec is None:
        raise ValueError("unknown strategy")
    val = rec.validation or {}
    if int(val.get("sample_size") or 0) < MIN_SAMPLE:
        raise ValueError(f"cannot approve: validation sample {val.get('sample_size', 0)} < {MIN_SAMPLE}")
    if rec.status == "RETIRED":
        raise ValueError("retired strategies cannot be approved; create a new version")
    if rec.status == "SUSPENDED":
        raise ValueError("suspended strategy: use reactivate()")
    th = threshold if threshold is not None else val.get("proposed_threshold")
    if th is None:
        raise ValueError("no threshold: run validation or pass one explicitly")
    if not note or len(note.strip()) < 10:
        raise ValueError("approval note must explain the decision (>=10 chars)")
    rec.status = "APPROVED"
    rec.production_threshold = float(th)
    rec.approval_note = note.strip() + (f" [validated on {val.get('data_label')} data]" if val.get("data_label") else "")
    _history(rec, {"action": "approved", "actor": actor, "note": note, "threshold": float(th), "validation_sample": val.get("sample_size"), "data_label": val.get("data_label")})
    db.commit()
    audit.record(db, actor, "strategy.approved", sid, {"threshold": float(th), "note": note, "data_label": val.get("data_label")})
    return rec


def suspend(db: Session, sid: str, actor: str, reason: str) -> StrategyRecord:
    rec = db.get(StrategyRecord, sid)
    if rec is None:
        raise ValueError("unknown strategy")
    if rec.status != "APPROVED":
        return rec
    rec.status = "SUSPENDED"
    rec.suspension_reason = reason
    _history(rec, {"action": "suspended", "actor": actor, "reason": reason, "version": rec.version})
    db.commit()
    audit.record(db, actor, "strategy.suspended", sid, {"reason": reason})
    return rec


def reactivate(db: Session, sid: str, actor: str, note: str) -> StrategyRecord:
    rec = db.get(StrategyRecord, sid)
    if rec is None or rec.status != "SUSPENDED":
        raise ValueError("only suspended strategies can be reactivated")
    hist = rec.approval_history or []
    last_susp = next((h for h in reversed(hist) if h.get("action") == "suspended"), None)
    val = rec.validation or {}
    revalidated = bool(val.get("validated_at") and last_susp and val["validated_at"] > last_susp["ts"])
    version_changed = bool(last_susp and last_susp.get("version") != rec.version)
    if not (revalidated or version_changed):
        raise ValueError("reactivation requires a new validation run after the suspension or a version change")
    prior_susp = sum(1 for h in hist if h.get("action") == "suspended" and h.get("version") == rec.version)
    if prior_susp >= 2 and not version_changed:
        rec.status = "RETIRED"
        _history(rec, {"action": "retired", "actor": actor, "reason": "two suspensions without version change"})
        db.commit()
        raise ValueError("strategy retired: two suspensions on the same version")
    rec.status = "APPROVED"
    rec.suspension_reason = None
    _history(rec, {"action": "reactivated", "actor": actor, "note": note})
    db.commit()
    audit.record(db, actor, "strategy.reactivated", sid, {"note": note})
    return rec


def retire(db: Session, sid: str, actor: str, reason: str) -> StrategyRecord:
    rec = db.get(StrategyRecord, sid)
    if rec is None:
        raise ValueError("unknown strategy")
    rec.status = "RETIRED"
    _history(rec, {"action": "retired", "actor": actor, "reason": reason})
    db.commit()
    audit.record(db, actor, "strategy.retired", sid, {"reason": reason})
    return rec


def rolling_stats(trades: list[TradeRecord], n: int) -> dict:
    recent = sorted(trades, key=lambda t: t.exit_ts)[-n:]
    if not recent:
        return {"trades": 0}
    rs = [t.r for t in recent]
    wins = [t for t in recent if t.win]
    gp = sum(t.pnl_usd for t in wins)
    gl = -sum(t.pnl_usd for t in recent if not t.win)
    peak = cur = mdd = 0.0
    for r in rs:
        cur += r
        peak = max(peak, cur)
        mdd = max(mdd, peak - cur)
    return {"trades": len(recent), "expectancy_r": sum(rs) / len(rs), "win_rate": len(wins) / len(recent), "profit_factor": (gp / gl) if gl > 0 else None, "drawdown_r": mdd}


def check_degradation(db: Session, sid: str, definition: StrategyDefinition, paper_trades: list[TradeRecord], actor: str = "monitor") -> dict:
    """Suspend the strategy when rolling paper performance breaches its suspension rules."""
    rules = definition.suspension_rules
    stats = rolling_stats(paper_trades, int(rules.get("rolling_trades", 30)))
    rec = db.get(StrategyRecord, sid)
    if rec is not None:
        rec.paper_results = stats | {"updated_at": datetime.now(tz=UTC).isoformat()}
        db.commit()
    breaches = []
    if stats.get("trades", 0) >= int(rules.get("rolling_trades", 30)):
        if stats["expectancy_r"] < float(rules.get("min_rolling_expectancy_r", 0.0)):
            breaches.append(f"rolling expectancy {stats['expectancy_r']:.2f}R below {rules.get('min_rolling_expectancy_r')}")
        if stats["drawdown_r"] > float(rules.get("max_rolling_drawdown_r", 8.0)):
            breaches.append(f"rolling drawdown {stats['drawdown_r']:.1f}R above {rules.get('max_rolling_drawdown_r')}")
        pf = stats.get("profit_factor")
        if pf is not None and pf < float(rules.get("min_rolling_profit_factor", 0.9)):
            breaches.append(f"rolling profit factor {pf:.2f} below {rules.get('min_rolling_profit_factor')}")
    if breaches and rec is not None and rec.status == "APPROVED":
        suspend(db, sid, actor, "; ".join(breaches))
    return {"stats": stats, "breaches": breaches}
