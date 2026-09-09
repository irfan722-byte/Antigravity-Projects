"""Analysis loop: one deterministic pass per tick.

For every onboarded user: advance the paper engine, compute the account state,
evaluate all horizons, persist changed decisions, emit notifications and SSE
events, run Friday / event / outcome housekeeping. Idempotent per (user, as_of):
a repeated call with the same as_of does not duplicate rows."""
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..core.candles import Timeframe
from ..core.contract_spec import get_spec
from ..core.decision import DecisionEngine, MarketSnapshot, UserContext
from ..core.integrity import DataStatus
from ..core.risk import RiskLimits, lock_status
from ..core.setup import Decision, Horizon
from ..core.strategies import build_strategies
from ..core.timeutil import friday_cutoff_utc
from ..db.models import AnalysisRun, DecisionOutcome, DecisionRecord, ProviderHealthRecord, User, UserSettings
from ..paper.engine import OrderStatus
from ..providers.registry import ProviderSet
from . import audit, strategy_service
from .bus import bus
from .notifications_glue import NotificationGlue
from .paper_service import PaperService
from .snapshot import build_snapshot

UTC = UTC
HEARTBEAT = timedelta(minutes=15)


def _limits(us: UserSettings) -> RiskLimits:
    base = RiskLimits.defaults().to_dict()
    base.update({k: v for k, v in (us.risk_limits or {}).items() if k in base})
    return RiskLimits(**base)


def needs_m1(engine, pending_outcomes: list) -> bool:
    """Whether minute candles can change anything this run.

    They can only matter with an open position, a resting order, or an expired setup still to be
    scored. Fetching them regardless cost an API credit per run on an idle account.
    """
    if engine.open_positions() or pending_outcomes:
        return True
    return any(o.status in (OrderStatus.PENDING, OrderStatus.PARTIAL) for o in engine.orders.values())


class AnalysisService:
    def __init__(self, providers: ProviderSet, settings: Settings | None = None):
        self.providers = providers
        self.settings = settings or get_settings()
        self.engine = DecisionEngine()
        self.strategies = build_strategies()
        self._last_m1: dict[str, datetime] = {}
        self._last_phase: dict[str, str] = {}
        self._friday_done: dict[str, str] = {}

    def strategies_by_horizon(self):
        out: dict[Horizon, list] = {}
        for s in self.strategies.values():
            out.setdefault(Horizon(s.definition.horizon), []).append(s)
        return out

    # ----------------------------------------------------------- tick ---
    def run_once(self, db: Session, now: datetime | None = None) -> dict:
        t0 = time.perf_counter()
        now = (now or datetime.now(tz=UTC)).astimezone(UTC).replace(second=0, microsecond=0)
        strategy_service.ensure_records(db)
        states = strategy_service.runtime_states(db)
        snap = build_snapshot(self.providers, now, "UTC")
        db.add(ProviderHealthRecord(ts=now, payload=[h.to_dict() for h in self.providers.health()]))
        users = db.query(User).filter(User.onboarding_completed.is_(True), User.deleted_at.is_(None)).all()
        summary = {"users": 0, "decisions": 0, "notifications": 0, "as_of": now.isoformat()}
        for user in users:
            us = user.settings
            if us is None:
                continue
            try:
                r = self._run_user(db, user, us, snap, states, now)
                summary["users"] += 1
                summary["decisions"] += r["decisions"]
                summary["notifications"] += r["notifications"]
            except Exception as exc:  # noqa: BLE001 - one user's failure must not stop the loop
                audit.record(db, "scheduler", "analysis.user_error", user.id, {"error": str(exc)[:500]})
        status = DataStatus.INVALID if (snap.quote_report is None or snap.quote_report.status == DataStatus.INVALID) else DataStatus.VALID
        db.add(AnalysisRun(ts=datetime.now(tz=UTC), as_of=now, users=summary["users"], duration_ms=(time.perf_counter() - t0) * 1000, data_status=status.value, detail=summary))
        db.commit()
        bus.publish("*", "analysis_run", summary)
        return summary

    def _run_user(self, db: Session, user: User, us: UserSettings, snap: MarketSnapshot, states, now: datetime) -> dict:
        limits = _limits(us)
        spec = get_spec(us.contract_spec_id)
        paper = PaperService(db, spec)
        glue = NotificationGlue(db, self.providers.push, user, us, self.settings)
        eng = paper.load_engine(user.id)
        # 1. advance paper engine with M1 candles closed since the last step.
        # M1 is not part of the snapshot, so this fetch costs an API credit on every run even when
        # nothing can move - about 288 a day at a five-minute interval, enough on its own to push
        # the free tier past its 800. Fetch only when there is an open position, a resting order,
        # or an expired setup whose outcome is still to be recorded.
        pending_outcomes = self._pending_outcomes(db, user.id, now)
        m1 = snap.candles.get(Timeframe.M1) or (self.providers.market.get_candles("XAUUSD", Timeframe.M1, now - timedelta(hours=6), now) if needs_m1(eng, pending_outcomes) else [])
        last = self._last_m1.get(user.id) or (eng._last_ts or now - timedelta(hours=6))
        new_m1 = [c for c in m1 if c.complete and c.end_ts > last]
        notable = paper.step(user.id, eng, new_m1, snap.quote)
        if new_m1:
            self._last_m1[user.id] = new_m1[-1].end_ts
        n_notif = 0
        for ev in notable:
            n_notif += glue.paper_event(ev, now)
        # 2. account & user context
        equity = limits.account_equity if limits.account_currency == "USD" else limits.account_equity / self.settings.usd_aed_rate
        account = paper.account_state(user.id, eng, equity, now)
        uctx = UserContext(user.id, us.timezone, limits, account, spec)
        # 3. decisions
        decisions = self.engine.evaluate_all(snap, uctx, self.strategies_by_horizon(), states)
        n_dec = 0
        for h, d in decisions.items():
            d.user_timezone = us.timezone
            prev = db.query(DecisionRecord).filter(DecisionRecord.user_id == user.id, DecisionRecord.horizon == h.value).order_by(desc(DecisionRecord.as_of)).first()
            if prev and prev.as_of.replace(tzinfo=UTC) == now:
                continue  # idempotent per (user, horizon, as_of)
            changed = prev is None or prev.status != d.status.value or prev.strategy_id != d.strategy_id or (d.setup and (prev.setup or {}).get("stop_loss") != d.setup.stop_loss) or now - prev.as_of.replace(tzinfo=UTC) >= HEARTBEAT
            if not changed:
                continue
            d.evidence_inspector["previous_status"] = prev.status if prev else None
            self._persist_decision(db, user.id, d)
            n_dec += 1
            bus.publish(user.id, "decision", {"horizon": h.value, "status": d.status.value, "decision_id": d.decision_id, "reason": d.reason})
            if prev is None or prev.status != d.status.value or (d.setup and (prev.setup or {}).get("stop_loss") != d.setup.stop_loss):
                n_notif += glue.decision(d, prev.status if prev else None, now)
            # optional automatic paper entry
            if d.setup and d.setup.entry_confirmed and (us.notification_prefs or {}).get("auto_paper_trade", False):
                try:
                    paper.place_from_decision(user.id, eng, d, limits, account, now, "auto-paper")
                    if snap.quote:
                        paper.step(user.id, eng, [], snap.quote)
                    else:
                        paper.persist(user.id, eng)
                except ValueError as exc:
                    audit.record(db, "auto-paper", "paper.auto_entry_skipped", d.decision_id, {"reason": str(exc)})
        # 4. news phase transitions
        phase = snap.news.phase.value
        prev_phase = self._last_phase.get(user.id)
        if phase != prev_phase:
            n_notif += glue.news_transition(prev_phase, snap.news, now)
            self._last_phase[user.id] = phase
        # 5. risk locks
        locks = lock_status(limits, account, now)
        if any(v for k, v in locks.items() if k.endswith("_locked")):
            n_notif += glue.risk_lock(locks, now)
        # 6. Friday workflow
        n_notif += self._friday(db, user, us, limits, paper, eng, snap, now, glue)
        # 7. outcomes for expired decisions
        self._record_outcomes(db, pending_outcomes, m1)
        return {"decisions": n_dec, "notifications": n_notif}

    def _persist_decision(self, db: Session, user_id: str, d: Decision) -> None:
        d.evidence_inspector["evidence_inspector_ref"] = f"/evidence/{d.decision_id}"
        if d.setup:
            d.setup.evidence_inspector_ref = f"/evidence/{d.decision_id}"
            d.setup.notification_timestamp = datetime.now(tz=UTC)
        db.add(DecisionRecord(id=d.decision_id, user_id=user_id, horizon=d.horizon, status=d.status.value, strategy_id=d.strategy_id, strategy_version=d.strategy_version, as_of=d.as_of, reason=d.reason, score=d.score, regime=d.regime, demo_data=d.demo_data, setup=d.setup.to_dict() if d.setup else None, evidence=d.evidence_inspector, expiry=d.setup.expiry if d.setup else None))
        db.commit()

    def _friday(self, db, user, us, limits: RiskLimits, paper: PaperService, eng, snap: MarketSnapshot, now: datetime, glue: NotificationGlue) -> int:
        n = 0
        cutoff = friday_cutoff_utc(now, us.timezone, limits.friday_cutoff_local)
        key = f"{user.id}:{cutoff.date()}"
        review_at = cutoff - timedelta(hours=1)
        if review_at <= now < cutoff and self._friday_done.get(key) != "review" and self._friday_done.get(key) != "closed":
            n += glue.friday_review(eng.open_positions(), cutoff, now)
            self._friday_done[key] = "review"
        if now >= cutoff and now < cutoff + timedelta(hours=6) and self._friday_done.get(key) != "closed":
            open_pos = eng.open_positions()
            weekly = [p for p in open_pos if p.horizon in ("WEEKLY", "SWING")]
            if weekly and limits.friday_auto_close_paper and snap.quote and us.weekend_risk_ack_at is None:
                closed = paper.close_all(user.id, eng, snap.quote, "friday_close", "scheduler")
                n += glue.friday_closed(closed, now)
            elif weekly:
                n += glue.weekend_gap_warning(weekly, now, override=us.weekend_risk_ack_at is not None)
            self._friday_done[key] = "closed"
        return n

    def _pending_outcomes(self, db: Session, user_id: str, now: datetime) -> list[DecisionRecord]:
        """Expired setups whose outcome has not been scored yet."""
        rows = db.query(DecisionRecord).filter(DecisionRecord.user_id == user_id, DecisionRecord.status.in_(["BUY_SETUP", "SELL_SETUP"]), DecisionRecord.expiry.isnot(None), DecisionRecord.expiry <= now).all()
        return [r for r in rows if not db.query(DecisionOutcome).filter(DecisionOutcome.decision_id == r.id).first()]

    def _record_outcomes(self, db: Session, rows: list[DecisionRecord], m1: list) -> None:
        # M1 is passed in rather than read from the snapshot: the snapshot never carries it, so
        # this silently recorded nothing whenever the paper engine had not already fetched it.
        for r in rows:
            s = r.setup or {}
            window = [c for c in m1 if r.as_of.replace(tzinfo=UTC) <= c.ts <= r.expiry.replace(tzinfo=UTC)]
            if not window:
                continue
            entry, stop = s.get("entry_reference"), s.get("stop_loss")
            tps = [t["price"] for t in s.get("targets", [])]
            direction = s.get("direction")
            mfe = mae = 0.0
            outcome = "EXPIRED"
            for c in window:
                if direction == "BUY":
                    mfe, mae = max(mfe, c.high - entry), max(mae, entry - c.low)
                    if c.low <= stop:
                        outcome = "STOP"
                        break
                    if tps and c.high >= tps[0]:
                        outcome = "TP2" if len(tps) > 1 and c.high >= tps[1] else "TP1"
                        if outcome == "TP2":
                            break
                else:
                    mfe, mae = max(mfe, entry - c.low), max(mae, c.high - entry)
                    if c.high >= stop:
                        outcome = "STOP"
                        break
                    if tps and c.low <= tps[0]:
                        outcome = "TP2" if len(tps) > 1 and c.low <= tps[1] else "TP1"
                        if outcome == "TP2":
                            break
            db.add(DecisionOutcome(decision_id=r.id, outcome=outcome, max_favourable_excursion=round(mfe, 2), max_adverse_excursion=round(mae, 2), detail={"basis": "M1 mid path within the setup window; no fill simulation", "bars": len(window)}))
        db.commit()
