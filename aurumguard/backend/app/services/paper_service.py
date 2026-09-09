"""Paper-trading service: persists PaperEngine state, enforces risk server-side,
computes the account state used by the gates, and produces journal/equity views."""
from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..backtest.metrics import TradeRecord, compute_metrics
from ..core.candles import Candle, Quote
from ..core.contract_spec import ContractSpec
from ..core.risk import AccountState, OpenRisk, RiskLimits, risk_checks
from ..core.setup import Decision, DecisionStatus
from ..core.timeutil import day_start_utc, week_start_utc
from ..db.models import PaperEventRecord, PaperOrderRecord, PaperPositionRecord
from ..paper.engine import Fill, OrderStatus, OrderType, PaperEngine, PaperOrder, PaperPosition, PositionStatus, SlippageParams
from . import audit

UTC = UTC


class PaperService:
    def __init__(self, db: Session, spec: ContractSpec):
        self.db = db
        self.spec = spec

    # ------------------------------------------------------------ engine --
    def load_engine(self, user_id: str) -> PaperEngine:
        eng = PaperEngine(self.spec, SlippageParams())
        for rec in self.db.query(PaperPositionRecord).filter(PaperPositionRecord.user_id == user_id).all():
            p = rec.payload
            pos = PaperPosition(rec.id, rec.order_id, rec.decision_id, user_id, rec.strategy_id, rec.strategy_version, rec.horizon, rec.direction, rec.lots_initial, rec.lots_open, rec.entry_price, rec.entry_ts.replace(tzinfo=UTC), rec.stop, rec.initial_stop, rec.tp1, rec.tp2, p.get("tp3"), datetime.fromisoformat(p["max_holding_until"]) if p.get("max_holding_until") else None, p.get("partial_close_at_tp1_pct", 50.0), p.get("move_to_breakeven_after_tp1", False), rec.risk_usd, PositionStatus(rec.status), p.get("tp1_hit", False), p.get("tp2_hit", False), rec.realised_pnl_usd, [Fill(datetime.fromisoformat(f["ts"]), f["price"], f["lots"], f["kind"], f.get("label", ""), f.get("slippage", 0.0), f.get("spread", 0.0)) for f in p.get("fills", [])], rec.exit_reason, rec.exit_ts.replace(tzinfo=UTC) if rec.exit_ts else None, p.get("modifications", []), p.get("meta", {}))
            eng.positions[pos.position_id] = pos
        for rec in self.db.query(PaperOrderRecord).filter(PaperOrderRecord.user_id == user_id, PaperOrderRecord.status.in_(["PENDING", "PARTIAL"])).all():
            p = rec.payload
            o = PaperOrder(rec.id, rec.decision_id, rec.strategy_id, p["strategy_version"], rec.horizon, rec.direction, OrderType(rec.order_type), rec.lots, p["stop"], p["tp1"], p["tp2"], datetime.fromisoformat(p["expiry"]), datetime.fromisoformat(p["max_holding_until"]) if p.get("max_holding_until") else None, p["max_spread"], rec.created_at.replace(tzinfo=UTC), p.get("limit_price"), p.get("tp3"), p.get("partial_close_at_tp1_pct", 50.0), p.get("move_to_breakeven_after_tp1", False), p.get("risk_usd", 0.0), OrderStatus(rec.status), p.get("filled_lots", 0.0), None, user_id, p.get("meta", {}))
            eng.orders[o.order_id] = o
        eng._seq = int(self.db.query(PaperEventRecord).filter(PaperEventRecord.user_id == user_id).count()) + len(eng.positions) + len(eng.orders)
        return eng

    def persist(self, user_id: str, eng: PaperEngine) -> None:
        for o in eng.orders.values():
            rec = self.db.get(PaperOrderRecord, o.order_id)
            payload = {"strategy_version": o.strategy_version, "stop": o.stop, "tp1": o.tp1, "tp2": o.tp2, "tp3": o.tp3, "expiry": o.expiry.isoformat(), "max_holding_until": o.max_holding_until.isoformat() if o.max_holding_until else None, "max_spread": o.max_spread, "limit_price": o.limit_price, "partial_close_at_tp1_pct": o.partial_close_at_tp1_pct, "move_to_breakeven_after_tp1": o.move_to_breakeven_after_tp1, "risk_usd": o.risk_usd, "filled_lots": o.filled_lots, "reject_reason": o.reject_reason, "meta": o.meta}
            if rec is None:
                self.db.add(PaperOrderRecord(id=o.order_id, user_id=user_id, decision_id=o.decision_id, strategy_id=o.strategy_id, horizon=o.horizon, direction=o.direction, order_type=o.order_type.value, lots=o.lots, status=o.status.value, payload=payload, created_at=o.created_at))
            else:
                rec.status, rec.payload = o.status.value, payload
        for p in eng.positions.values():
            rec = self.db.get(PaperPositionRecord, p.position_id)
            payload = {"tp3": p.tp3, "max_holding_until": p.max_holding_until.isoformat() if p.max_holding_until else None, "partial_close_at_tp1_pct": p.partial_close_at_tp1_pct, "move_to_breakeven_after_tp1": p.move_to_breakeven_after_tp1, "tp1_hit": p.tp1_hit, "tp2_hit": p.tp2_hit, "fills": [{"ts": f.ts.isoformat(), "price": f.price, "lots": f.lots, "kind": f.kind, "label": f.label, "slippage": f.slippage, "spread": f.spread} for f in p.fills], "modifications": p.modifications, "meta": p.meta}
            if rec is None:
                self.db.add(PaperPositionRecord(id=p.position_id, user_id=user_id, order_id=p.order_id, decision_id=p.decision_id, strategy_id=p.strategy_id, strategy_version=p.strategy_version, horizon=p.horizon, direction=p.direction, status=p.status.value, entry_ts=p.entry_ts, exit_ts=p.exit_ts, entry_price=p.entry_price, lots_initial=p.lots_initial, lots_open=p.lots_open, stop=p.stop, initial_stop=p.initial_stop, tp1=p.tp1, tp2=p.tp2, risk_usd=p.risk_usd, realised_pnl_usd=p.realised_pnl_usd, exit_reason=p.exit_reason, payload=payload))
            else:
                rec.status, rec.exit_ts, rec.lots_open, rec.stop, rec.realised_pnl_usd, rec.exit_reason, rec.payload = p.status.value, p.exit_ts, p.lots_open, p.stop, p.realised_pnl_usd, p.exit_reason, payload
        for ev in eng.events:
            self.db.add(PaperEventRecord(user_id=user_id, ts=ev.ts, kind=ev.kind, ref_id=ev.ref_id, detail=ev.detail))
        eng.events.clear()
        self.db.commit()

    # ------------------------------------------------------- account ----
    def closed_trades(self, user_id: str) -> list[TradeRecord]:
        out = []
        for r in self.db.query(PaperPositionRecord).filter(PaperPositionRecord.user_id == user_id, PaperPositionRecord.status == "CLOSED").order_by(PaperPositionRecord.exit_ts).all():
            fills = r.payload.get("fills", [])
            exit_price = fills[-1]["price"] if fills else r.entry_price
            meta = r.payload.get("meta", {})
            gross = (1 if r.direction == "BUY" else -1) * (exit_price - r.entry_price) * r.lots_initial * self.spec.contract_size_oz
            out.append(TradeRecord(r.id, r.strategy_id, r.strategy_version, r.horizon, r.direction, r.entry_ts.replace(tzinfo=UTC), (r.exit_ts or r.entry_ts).replace(tzinfo=UTC), r.entry_price, exit_price, r.lots_initial, r.risk_usd, r.realised_pnl_usd, gross, gross - r.realised_pnl_usd, r.exit_reason or "", meta.get("session", ""), meta.get("regime", ""), meta.get("score"), meta.get("near_event", False), " ".join(f.get("label", "") for f in fills).strip(), meta.get("calibrated_p")))
        return out

    def account_state(self, user_id: str, eng: PaperEngine, starting_equity_usd: float, now: datetime) -> AccountState:
        trades = self.closed_trades(user_id)
        realised_total = sum(t.pnl_usd for t in trades)
        d0, w0 = day_start_utc(now), week_start_utc(now)
        today = sum(t.pnl_usd for t in trades if t.exit_ts >= d0)
        week = sum(t.pnl_usd for t in trades if t.exit_ts >= w0)
        m0 = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        eq = starting_equity_usd
        peak = starting_equity_usd + sum(t.pnl_usd for t in trades if t.exit_ts < m0)
        running = peak
        for t in trades:
            if t.exit_ts >= m0:
                running += t.pnl_usd
                peak = max(peak, running)
        eq = starting_equity_usd + realised_total
        streak = 0
        for t in reversed(trades):
            if t.win:
                break
            streak += 1
        opened_today = sum(1 for p in eng.positions.values() if p.entry_ts >= d0)
        open_risks = []
        for p in eng.open_positions():
            sign = 1 if p.direction == "BUY" else -1
            open_risks.append(OpenRisk(p.position_id, p.strategy_id, p.horizon, p.direction, max(0.0, sign * (p.entry_price - p.stop)) * p.lots_open * self.spec.contract_size_oz))
        return AccountState(eq, today, week, max(peak, eq), open_risks, opened_today, streak)

    # --------------------------------------------------------- orders ----
    def place_from_decision(self, user_id: str, eng: PaperEngine, decision: Decision, limits: RiskLimits, account: AccountState, now: datetime, actor: str) -> PaperOrder:
        """Server-side entry: re-runs the risk checks so no client can bypass them."""
        if decision.status not in (DecisionStatus.BUY_SETUP, DecisionStatus.SELL_SETUP) or decision.setup is None:
            raise ValueError("decision has no actionable setup")
        s = decision.setup
        if now >= s.expiry:
            raise ValueError("setup has expired")
        size = s.position_size
        if size.get("status") != "OK" or size.get("lots", 0) <= 0:
            raise ValueError(f"position size not valid: {size.get('status')}")
        checks = risk_checks(limits, account, float(size["risk_usd"]), now)
        failed = [f"{k}: {v[1]}" for k, v in checks.items() if not v[0]]
        if failed:
            audit.record(self.db, actor, "paper.order_blocked", decision.decision_id, {"failed": failed})
            raise ValueError("risk limits block this order: " + "; ".join(failed))
        if any(p.decision_id == decision.decision_id for p in eng.positions.values()) or any(o.decision_id == decision.decision_id and o.status in (OrderStatus.PENDING, OrderStatus.PARTIAL) for o in eng.orders.values()):
            raise ValueError("an order for this decision already exists")
        tp3 = next((t.price for t in s.targets if t.label == "TP3"), None)
        order = PaperOrder(f"ord_{uuid.uuid4().hex[:12]}", decision.decision_id, s.strategy_id, s.strategy_version, s.horizon, s.direction, OrderType.MARKET, float(size["lots"]), s.stop_loss, s.targets[0].price, s.targets[1].price, s.expiry, s.max_holding_until, min(limits.max_spread_usd, s.estimated_spread * 2 + 0.2), now, tp3=tp3, risk_usd=float(size["risk_usd"]), user_id=user_id, meta={"session": s.market_regime.get("measurements", {}).get("session"), "regime": s.market_regime.get("primary"), "score": decision.score, "near_event": s.news_risk.get("phase") != "NONE", "calibrated_p": (s.confidence_low + s.confidence_high) / 2})
        eng.submit(order)
        audit.record(self.db, actor, "paper.order_submitted", order.order_id, {"decision_id": decision.decision_id, "lots": order.lots, "risk_usd": order.risk_usd, "status": order.status.value})
        return order

    def step(self, user_id: str, eng: PaperEngine, candles: list[Candle], quote: Quote | None) -> list[dict]:
        """Advance the engine through new closed candles then the current quote. Returns notable events."""
        before = {p.position_id: (p.status, p.tp1_hit, p.tp2_hit) for p in eng.positions.values()}
        for c in candles:
            if eng._last_ts is None or c.end_ts >= eng._last_ts:
                eng.on_candle(c)
        if quote is not None and (eng._last_ts is None or quote.ts >= eng._last_ts):
            eng.on_quote(quote)
        notable = []
        for p in eng.positions.values():
            b = before.get(p.position_id)
            if b is None:
                notable.append({"kind": "OPENED", "position": p})
                continue
            if not b[1] and p.tp1_hit:
                notable.append({"kind": "PAPER_TP1", "position": p})
            if not b[2] and p.tp2_hit:
                notable.append({"kind": "PAPER_TP2", "position": p})
            if b[0] == PositionStatus.OPEN and p.status == PositionStatus.CLOSED and p.exit_reason == "stop":
                notable.append({"kind": "PAPER_STOP", "position": p})
            elif b[0] == PositionStatus.OPEN and p.status == PositionStatus.CLOSED:
                notable.append({"kind": "CLOSED", "position": p})
        self.persist(user_id, eng)
        return notable

    def close_all(self, user_id: str, eng: PaperEngine, quote: Quote, reason: str, actor: str) -> list[str]:
        closed = eng.close_all(quote, reason)
        self.persist(user_id, eng)
        if closed:
            audit.record(self.db, actor, f"paper.close_all.{reason}", user_id, {"positions": closed})
        return closed

    # -------------------------------------------------------- reports ----
    def journal(self, user_id: str) -> list[dict]:
        return [t.to_dict() for t in self.closed_trades(user_id)]

    def performance(self, user_id: str, starting_equity: float, since: datetime | None = None) -> dict:
        trades = self.closed_trades(user_id)
        if since:
            trades = [t for t in trades if t.exit_ts >= since]
        if not trades:
            return {"label": "PAPER", "trades": 0}
        period = max(1.0, (trades[-1].exit_ts - trades[0].entry_ts).total_seconds() / 86400)
        by_strategy = {}
        for sid in sorted({t.strategy_id for t in trades}):
            by_strategy[sid] = compute_metrics([t for t in trades if t.strategy_id == sid], starting_equity, period, f"PAPER:{sid}")
        by_horizon = {}
        for h in sorted({t.horizon for t in trades}):
            by_horizon[h] = compute_metrics([t for t in trades if t.horizon == h], starting_equity, period, f"PAPER:{h}")
        return {"portfolio": compute_metrics(trades, starting_equity, period, "PAPER"), "by_strategy": by_strategy, "by_horizon": by_horizon}

    def events(self, user_id: str, limit: int = 200) -> list[dict]:
        rows = self.db.query(PaperEventRecord).filter(PaperEventRecord.user_id == user_id).order_by(PaperEventRecord.ts.desc()).limit(limit).all()
        return [{"ts": r.ts.isoformat(), "kind": r.kind, "ref_id": r.ref_id, "detail": r.detail} for r in rows]

    @staticmethod
    def position_dict(p: PaperPosition) -> dict:
        d = asdict(p)
        d["status"] = p.status.value
        d["entry_ts"] = p.entry_ts.isoformat()
        d["exit_ts"] = p.exit_ts.isoformat() if p.exit_ts else None
        d["max_holding_until"] = p.max_holding_until.isoformat() if p.max_holding_until else None
        d["fills"] = [{"ts": f.ts.isoformat(), "price": f.price, "lots": f.lots, "kind": f.kind, "label": f.label, "slippage": f.slippage, "spread": f.spread} for f in p.fills]
        d["r_multiple"] = p.r_multiple
        return d
