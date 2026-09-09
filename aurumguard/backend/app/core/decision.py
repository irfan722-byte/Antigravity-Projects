"""Decision engine: one auditable decision per horizon.

Order of evaluation (each step can end the evaluation with a definite status):
  1. data integrity        -> DATA_UNAVAILABLE
  2. market/calendar state -> NO_TRADE (closed) / DATA_UNAVAILABLE (unverified calendar)
  3. news state machine    -> EVENT_LOCKOUT
  4. structure + regime
  5. approved strategies   -> proposals
  6. costs, sizing, R:R, risk checks, calibration, scoring, hard gates
  7. BUY_SETUP / SELL_SETUP / WAIT / NO_TRADE with full Evidence Inspector
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..config import load_json_config
from .calibration import CALIBRATION_VERSION, calibrated_probability
from .candles import Candle, Quote, Timeframe
from .contract_spec import ContractSpec
from .evidence import Evidence, Family, ScoreBreakdown, score_evidence
from .gates import GateContext, evaluate_gates, failed_codes
from .integrity import DataStatus, IntegrityReport
from .news_state import NewsPhase, NewsState
from .regime import IntermarketInputs, Regime, RegimeAssessment, classify_regime
from .risk import AccountState, CostModel, RiskLimits, SizeStatus, compute_position_size, net_reward_to_risk, risk_checks
from .setup import UNCERTAINTY_STATEMENT, Decision, DecisionStatus, Horizon, Target, TradeSetup
from .strategies.base import Strategy, StrategyContext, StrategyProposal
from .structure import StructureParams, StructureSnapshot, analyse_structure
from .timeutil import MarketState, past_friday_cutoff

MODEL_VERSION = "decision-engine-v1"

HORIZON_TIMEFRAMES: dict[Horizon, list[Timeframe]] = {
    Horizon.SCALP: [Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1],
    Horizon.INTRADAY: [Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1],
    Horizon.SWING: [Timeframe.H1, Timeframe.H4, Timeframe.D1],
    Horizon.WEEKLY: [Timeframe.H4, Timeframe.D1, Timeframe.W1],
}

ANCHOR_TF: dict[Horizon, Timeframe] = {
    Horizon.SCALP: Timeframe.M15,
    Horizon.INTRADAY: Timeframe.H4,
    Horizon.SWING: Timeframe.H4,
    Horizon.WEEKLY: Timeframe.D1,
}


@dataclass
class StrategyRuntimeState:
    status: str  # RESEARCH | APPROVED | SUSPENDED | RETIRED
    validation: dict = field(default_factory=dict)  # from validation pipeline
    production_threshold: float | None = None
    suspension_reason: str | None = None
    approval_note: str = ""


@dataclass
class MarketSnapshot:
    as_of: datetime
    provider: str
    demo_data: bool
    quote: Quote | None
    quote_report: IntegrityReport | None
    candles: dict[Timeframe, list[Candle]]
    candle_reports: dict[Timeframe, IntegrityReport]
    news: NewsState
    session_label: str
    market_state: MarketState
    calendar_verified: bool
    provider_health_ok: bool
    provider_health_reason: str
    median_spread: float | None
    intermarket: IntermarketInputs | None = None
    intermarket_evidence: list[Evidence] = field(default_factory=list)
    macro_evidence: list[Evidence] = field(default_factory=list)
    positioning_evidence: list[Evidence] = field(default_factory=list)
    data_sources: dict[str, str] = field(default_factory=dict)
    data_unavailable: list[str] = field(default_factory=list)
    reaction_inputs: dict | None = None


@dataclass
class UserContext:
    user_id: str
    timezone: str
    limits: RiskLimits
    account: AccountState
    spec: ContractSpec
    weekly_new_setup_cutoff_hours_before: float = 4.0


def estimate_slippage(spread: float, session_label: str, vol_state: str) -> float:
    """Conservative deterministic slippage model (USD). Documented in docs/15-risk-management-specification.md."""
    base = 0.05 + 0.4 * spread
    if session_label == "OFF_HOURS":
        base *= 1.8
    elif session_label == "ASIA":
        base *= 1.3
    if vol_state == "EXPANSION":
        base *= 1.5
    return round(base, 2)


class DecisionEngine:
    def __init__(self, scoring_config: dict | None = None, structure_params: StructureParams | None = None):
        self.scoring = scoring_config or load_json_config("scoring_config.json")
        self.sp = structure_params or StructureParams()

    # ------------------------------------------------------------ helpers --
    def _decision_id(self, user_id: str, horizon: Horizon, as_of: datetime) -> str:
        return hashlib.sha256(f"{user_id}:{horizon.value}:{as_of.isoformat()}:{uuid.uuid4()}".encode()).hexdigest()[:20]

    def _inspector_base(self, snap: MarketSnapshot, horizon: Horizon, user: UserContext) -> dict:
        tfs = HORIZON_TIMEFRAMES[horizon]
        used = [f"XAUUSD {tf.value} candles ({len(snap.candles.get(tf, []))} closed bars)" for tf in tfs if snap.candles.get(tf)]
        unavailable = [f"XAUUSD {tf.value} candles" for tf in tfs if not snap.candles.get(tf)] + list(snap.data_unavailable)
        if snap.quote:
            used.append(f"XAUUSD quote bid {snap.quote.bid} ask {snap.quote.ask} @ {snap.quote.ts.isoformat()}")
        else:
            unavailable.append("XAUUSD live quote")
        return {
            "data_used": used,
            "data_unavailable": unavailable,
            "data_excluded": [],
            "data_sources": snap.data_sources | {"market_data": snap.provider},
            "timestamps": {"decision": snap.as_of.isoformat(), "quote": snap.quote.ts.isoformat() if snap.quote else None, **{f"last_{tf.value}": snap.candles[tf][-1].end_ts.isoformat() for tf in tfs if snap.candles.get(tf)}},
            "feature_values": {},
            "rules_triggered": [],
            "rules_not_triggered": [],
            "gates_passed": [],
            "gates_failed": [],
            "supporting": [],
            "contradictory": [],
            "regime": None,
            "model_version": MODEL_VERSION,
            "strategy_version": None,
            "scoring_config": self.scoring.get("version"),
            "calibration_version": CALIBRATION_VERSION,
            "risk_calculations": {},
            "known_limitations": [
                "Deterministic rules on public/licensed data; no private information.",
                "Historical comparables do not guarantee future outcomes.",
                "DEMO DATA: synthetic prices; nothing here reflects the real market." if snap.demo_data else "Provider data subject to licence terms and revisions.",
            ],
            "data_quality": {tf.value: r.to_dict() for tf, r in snap.candle_reports.items()} | ({"quote": snap.quote_report.to_dict()} if snap.quote_report else {}),
            "news_state": snap.news.to_dict(user.timezone),
            "decision_timestamp": snap.as_of.isoformat(),
            "outcome": None,
            "user_timezone": user.timezone,
        }

    def _finish(self, status: DecisionStatus, reason: str, snap: MarketSnapshot, horizon: Horizon, user: UserContext, inspector: dict, strategy: Strategy | None = None, setup: TradeSetup | None = None, score: float | None = None, regime: RegimeAssessment | None = None) -> Decision:
        inspector["decision_status"] = status.value
        inspector["decision_reason"] = reason
        return Decision(
            decision_id=self._decision_id(user.user_id, horizon, snap.as_of),
            status=status,
            horizon=horizon.value,
            strategy_id=strategy.id if strategy else None,
            strategy_version=strategy.definition.version if strategy else None,
            as_of=snap.as_of,
            reason=reason,
            setup=setup,
            evidence_inspector=inspector,
            score=score,
            regime=regime.primary.value if regime else None,
            demo_data=snap.demo_data,
            user_timezone=user.timezone,
        )

    # ------------------------------------------------------- main entry --
    def evaluate_horizon(self, snap: MarketSnapshot, user: UserContext, horizon: Horizon, strategies: list[Strategy], states: dict[str, StrategyRuntimeState]) -> Decision:
        insp = self._inspector_base(snap, horizon, user)
        tfs = HORIZON_TIMEFRAMES[horizon]

        # 1. data integrity
        problems: list[str] = []
        if snap.quote is None or snap.quote_report is None or snap.quote_report.status == DataStatus.INVALID:
            problems.append("live quote missing or invalid" + (f" ({'; '.join(snap.quote_report.codes())})" if snap.quote_report else ""))
        required = [tf for tf in tfs if tf in (Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1)] if horizon != Horizon.SCALP else [Timeframe.M5, Timeframe.M15]
        for tf in required:
            rep = snap.candle_reports.get(tf)
            if not snap.candles.get(tf) or rep is None or rep.status == DataStatus.INVALID:
                problems.append(f"{tf.value} candles missing or invalid" + (f" ({'; '.join(rep.codes())})" if rep else ""))
        if not snap.provider_health_ok:
            problems.append(f"provider health: {snap.provider_health_reason}")
        if problems:
            return self._finish(DecisionStatus.DATA_UNAVAILABLE, "; ".join(problems), snap, horizon, user, insp)

        # 2. market state / calendar
        if not snap.calendar_verified:
            return self._finish(DecisionStatus.DATA_UNAVAILABLE, "trading calendar could not be verified; holiday/early-close state unknown", snap, horizon, user, insp)
        if snap.market_state != MarketState.OPEN:
            return self._finish(DecisionStatus.NO_TRADE, f"market {snap.market_state.value}; no evaluation of new setups while closed", snap, horizon, user, insp)

        # 3. news state
        if snap.news.is_lockout:
            return self._finish(DecisionStatus.EVENT_LOCKOUT, "; ".join(snap.news.reasons) or snap.news.phase.value, snap, horizon, user, insp)

        # 4. structure + regime
        structures: dict[Timeframe, StructureSnapshot] = {}
        daily = snap.candles.get(Timeframe.D1) or []
        for tf in tfs:
            cs = snap.candles.get(tf)
            if cs and len(cs) >= self.sp.atr_period + 5:
                try:
                    structures[tf] = analyse_structure(cs, snap.as_of, self.sp, daily_candles=daily or None)
                except ValueError:
                    continue
        anchor = ANCHOR_TF[horizon]
        anchor_cs = snap.candles.get(anchor) or []
        regime = classify_regime(anchor_cs, structures.get(anchor), structures.get(Timeframe.D1) if anchor != Timeframe.D1 else None, snap.intermarket, snap.news.phase.value, snap.session_label, snap.quote.spread, snap.median_spread, snap.as_of)
        insp["regime"] = regime.to_dict()
        insp["feature_values"] = {tf.value: s.to_dict() for tf, s in structures.items()}

        # weekly horizon: Friday cutoff rules
        if horizon == Horizon.WEEKLY:
            cutoff_hours = user.weekly_new_setup_cutoff_hours_before
            probe = snap.as_of + timedelta(hours=cutoff_hours)
            if past_friday_cutoff(snap.as_of, user.timezone, user.limits.friday_cutoff_local) or past_friday_cutoff(probe, user.timezone, user.limits.friday_cutoff_local):
                return self._finish(DecisionStatus.NO_TRADE, f"no new weekly setups within {cutoff_hours:g}h of the Friday cutoff ({user.limits.friday_cutoff_local} {user.timezone})", snap, horizon, user, insp, regime=regime)

        # 5. strategies
        approved = [s for s in strategies if states.get(s.id, StrategyRuntimeState("RESEARCH")).status == "APPROVED"]
        if not strategies:
            return self._finish(DecisionStatus.NO_TRADE, f"no strategy implemented for the {horizon.value} horizon" + (" (scalping needs tick-level bid/ask history for validation; the current provider does not supply it)" if horizon == Horizon.SCALP else ""), snap, horizon, user, insp, regime=regime)
        if not approved:
            names = ", ".join(f"{s.id}({states.get(s.id, StrategyRuntimeState('RESEARCH')).status})" for s in strategies)
            return self._finish(DecisionStatus.NO_TRADE, f"no APPROVED strategy for {horizon.value}: {names}", snap, horizon, user, insp, regime=regime)

        proposals: list[tuple[Strategy, StrategyProposal]] = []
        not_triggered: dict[str, list[str]] = {}
        for s in approved:
            ctx = StrategyContext(
                as_of=snap.as_of,
                quote=snap.quote,
                candles=snap.candles,
                structures=structures,
                regime=regime,
                session_label=snap.session_label,
                news_phase=snap.news.phase.value,
                news_context=snap.news.to_dict(user.timezone),
                intermarket_evidence=snap.intermarket_evidence,
                macro_evidence=snap.macro_evidence,
                positioning_evidence=snap.positioning_evidence,
                structure_params=self.sp,
                latest_event_reaction=snap.news.reaction,
            )
            # regime pre-check to avoid evaluating strategies whose regime is prohibited (still recorded)
            regime_set = {regime.primary.value, *(t.value for t in regime.tags)}
            if regime.primary.value not in s.definition.approved_regimes or regime_set & set(s.definition.prohibited_regimes):
                not_triggered[s.id] = [f"regime {regime.primary.value} {sorted(regime_set)} not approved for {s.id}"]
                continue
            prop = s.evaluate(ctx)
            if prop is None:
                not_triggered[s.id] = ["entry setup conditions not met"]
                continue
            proposals.append((s, prop))
        insp["rules_not_triggered"] = [f"{k}: {'; '.join(v)}" for k, v in not_triggered.items()]
        if not proposals:
            return self._finish(DecisionStatus.NO_TRADE, "no approved strategy setup exists: " + "; ".join(f"{k} ({'; '.join(v)})" for k, v in not_triggered.items()), snap, horizon, user, insp, regime=regime)

        # 6. evaluate each proposal fully; choose the best passing one
        evaluated = []
        for s, prop in proposals:
            evaluated.append(self._evaluate_proposal(snap, user, horizon, s, prop, states.get(s.id, StrategyRuntimeState("APPROVED")), regime, structures))
        # preference: confirmed & all gates passed & highest score, then developing (WAIT), then NO_TRADE
        evaluated.sort(key=lambda e: (e["status_rank"], -(e["score"] or 0)))
        best = evaluated[0]
        insp.update(best["inspector_patch"])
        insp["other_candidates"] = [{"strategy": e["strategy"].id, "status": e["status"].value, "reason": e["reason"], "score": e["score"]} for e in evaluated[1:]]
        return self._finish(best["status"], best["reason"], snap, horizon, user, insp, best["strategy"], best.get("setup"), best["score"], regime)

    # ------------------------------------------------- proposal evaluation --
    def _evaluate_proposal(self, snap: MarketSnapshot, user: UserContext, horizon: Horizon, s: Strategy, prop: StrategyProposal, state: StrategyRuntimeState, regime: RegimeAssessment, structures: dict[Timeframe, StructureSnapshot]) -> dict:
        d = s.definition
        q = snap.quote
        vol_state = structures[ANCHOR_TF[horizon]].volatility if ANCHOR_TF[horizon] in structures else "UNKNOWN"
        slippage = estimate_slippage(q.spread, snap.session_label, vol_state)
        fin = 0.0
        if horizon in (Horizon.SWING, Horizon.WEEKLY) and prop.max_holding_until:
            days = max(1.0, (prop.max_holding_until - snap.as_of).total_seconds() / 86400)
            rate = user.spec.financing_long_annual_pct if prop.direction == "BUY" else user.spec.financing_short_annual_pct
            if rate is not None:
                fin = abs(rate) / 100 * prop.entry_reference * user.spec.contract_size_oz * days / 365 if rate < 0 else 0.0
        costs = CostModel(spread=q.spread, slippage_entry=slippage / 2, slippage_exit=slippage / 2, commission_per_lot_usd=user.spec.commission_per_lot_round_trip_usd, financing_estimate_usd=fin)
        risk_pct = user.limits.risk_per_trade_pct * (0.5 if s.id == "PNC-M15" else 1.0)
        size = compute_position_size(user.account.equity_usd, risk_pct, prop.entry_reference, prop.stop, prop.direction, costs, user.spec)
        rr1 = net_reward_to_risk(prop.entry_reference, prop.stop, prop.tp1, prop.direction, costs, user.spec)
        rr2 = net_reward_to_risk(prop.entry_reference, prop.stop, prop.tp2, prop.direction, costs, user.spec)
        rr3 = net_reward_to_risk(prop.entry_reference, prop.stop, prop.tp3, prop.direction, costs, user.spec) if prop.tp3 else None
        checks = risk_checks(user.limits, user.account, size.risk_usd if size.status == SizeStatus.OK else 0.0, snap.as_of)

        # evidence
        direction = 1 if prop.direction == "BUY" else -1
        items: list[Evidence] = list(prop.evidence) + list(snap.intermarket_evidence) + list(snap.macro_evidence) + list(snap.positioning_evidence)
        val = state.validation or {}
        if val.get("sample_size"):
            exp_r = val.get("expectancy_r")
            items.append(Evidence(Family.STRATEGY_HISTORY, f"{s.id}_history", direction if (exp_r or 0) > 0 else -direction, min(1.0, abs(exp_r or 0) / 0.5), f"{val.get('label', 'validation')} expectancy {exp_r:+.2f}R over {val['sample_size']} trades ({val.get('data_label', 'unknown data')})", "validation", snap.as_of))
        else:
            items.append(Evidence(Family.STRATEGY_HISTORY, f"{s.id}_history", 0, 0.0, "no validation sample recorded", "validation", snap.as_of, available=False))
        items.append(Evidence(Family.LIQUIDITY_EXECUTION, "spread_vs_limit", direction if q.spread <= d.spread_limit else -direction, min(1.0, 1 - q.spread / max(d.spread_limit, 1e-6)) if q.spread <= d.spread_limit else 0.8, f"spread {q.spread:.2f} vs limit {d.spread_limit:.2f}", "quote", snap.as_of))
        if snap.news.phase == NewsPhase.PRE_EVENT_WINDOW and snap.news.event:
            items.append(Evidence(Family.NEWS_EVENT, "pre_event_window", -direction, 0.5, f"{snap.news.event.name} in {(snap.news.seconds_to_event or 0) / 60:.0f} min", "calendar", snap.as_of))
        if regime.primary in (Regime.STRONG_TREND, Regime.WEAK_TREND) and regime.trend_direction != "NONE":
            items.append(Evidence(Family.VOLATILITY, "regime_trend", 1 if regime.trend_direction == "UP" else -1, regime.confidence, f"regime {regime.primary.value} {regime.trend_direction} conf {regime.confidence:.2f}", "regime", snap.as_of))
        score = score_evidence(items, direction, self.scoring)
        cal = calibrated_probability(val, score.score)
        threshold = state.production_threshold if state.production_threshold is not None else float(self.scoring.get("research_threshold", 75))
        threshold_note = "validated production threshold" if state.production_threshold is not None else "research threshold (no validated production threshold recorded)"

        max_spread = min(user.limits.max_spread_usd, d.spread_limit)
        max_slip = min(user.limits.max_expected_slippage_usd, d.slippage_limit)
        min_rr = max(user.limits.min_net_reward_to_risk, d.min_net_rr)
        gctx = GateContext(
            data_status=DataStatus.VALID,
            data_reasons=[],
            event_ts_verified=all(e.verification.value != "CONFLICT" for e in snap.news.upcoming) and (snap.news.event is None or snap.news.event.scheduled_ts.tzinfo is not None),
            spread=q.spread,
            max_spread=max_spread,
            expected_slippage=slippage,
            max_slippage=max_slip,
            session_label=snap.session_label,
            allowed_sessions=d.sessions,
            news_phase=snap.news.phase.value,
            strategy_status=state.status,
            regime_primary=regime.primary.value,
            regime_tags=[t.value for t in regime.tags],
            approved_regimes=d.approved_regimes,
            prohibited_regimes=d.prohibited_regimes,
            risk_checks=checks,
            net_rr_tp1=rr1,
            min_net_rr=min_rr,
            position_size_ok=size.status == SizeStatus.OK,
            position_size_reason=size.reason,
            econ_conflict_unresolved=snap.news.event is not None and snap.news.event.verification.value == "CONFLICT",
            provider_health_ok=snap.provider_health_ok,
            provider_health_reason=snap.provider_health_reason,
            probability_in_range=cal.in_range,
            probability_reason=cal.reason,
            calendar_verified=snap.calendar_verified,
            timezone_verified=True,
            price_confirmation_required=prop.confirmation_required,
            price_confirmed=prop.confirmed,
            market_open=snap.market_state == MarketState.OPEN,
        )
        gates = evaluate_gates(gctx)
        failed = failed_codes(gates)
        score_ok = score.score >= threshold
        min_fams = int(self.scoring.get("min_independent_families_supporting", 3))
        fams_ok = score.independent_families_supporting >= min_fams

        patch = {
            "strategy_version": d.version,
            "rules_triggered": prop.rules_triggered,
            "rules_not_triggered": prop.rules_not_triggered,
            "gates_passed": [g.to_dict() for g in gates if g.passed],
            "gates_failed": [g.to_dict() for g in gates if not g.passed and g.applicable],
            "supporting": [e.to_dict() for e in score.supporting],
            "contradictory": [e.to_dict() for e in score.contradicting],
            "score": score.to_dict(),
            "threshold": {"value": threshold, "note": threshold_note, "score_ok": score_ok, "independent_families": score.independent_families_supporting, "min_independent_families": min_fams},
            "calibration": cal.to_dict(),
            "risk_calculations": {"position_size": size.to_dict(), "net_rr_tp1": rr1, "net_rr_tp2": rr2, "net_rr_tp3": rr3, "costs": costs.__dict__, "risk_checks": {k: {"ok": v[0], "reason": v[1]} for k, v in checks.items()}},
            "proposal": {"direction": prop.direction, "entry_reference": prop.entry_reference, "stop": prop.stop, "tp1": prop.tp1, "tp2": prop.tp2, "developing": prop.developing, "note": prop.note},
        }

        if prop.developing:
            reason = f"{s.id}: setup developing; waiting for {', '.join(prop.rules_not_triggered) or 'trigger'}"
            other = [c for c in failed if c != "G20"]
            if other:
                reason += f"; also blocked by {other}"
            return {"status": DecisionStatus.WAIT, "status_rank": 1, "reason": reason, "score": score.score, "strategy": s, "inspector_patch": patch}
        if failed:
            names = {g.code: g.reason for g in gates}
            reason = f"{s.id}: hard gates failed: " + "; ".join(f"{c} ({names[c]})" for c in failed)
            return {"status": DecisionStatus.NO_TRADE, "status_rank": 2, "reason": reason, "score": score.score, "strategy": s, "inspector_patch": patch}
        if not score_ok or not fams_ok:
            reason = f"{s.id}: evidence score {score.score:.0f} vs threshold {threshold:.0f} ({threshold_note}); independent families {score.independent_families_supporting}/{min_fams}"
            return {"status": DecisionStatus.NO_TRADE, "status_rank": 2, "reason": reason, "score": score.score, "strategy": s, "inspector_patch": patch}

        setup = self._build_setup(snap, user, horizon, s, prop, size, rr1, rr2, rr3, costs, cal, val, state, regime, score, gates)
        status = DecisionStatus.BUY_SETUP if prop.direction == "BUY" else DecisionStatus.SELL_SETUP
        return {"status": status, "status_rank": 0, "reason": setup.decision_reason, "score": score.score, "strategy": s, "inspector_patch": patch, "setup": setup}

    def _build_setup(self, snap, user, horizon, s, prop, size, rr1, rr2, rr3, costs, cal, val, state, regime, score: ScoreBreakdown, gates) -> TradeSetup:
        d = s.definition
        q = snap.quote
        targets = [Target("TP1", prop.tp1, prop.tp1_rationale, rr1), Target("TP2", prop.tp2, prop.tp2_rationale, rr2)]
        if prop.tp3 is not None:
            targets.append(Target("TP3", prop.tp3, prop.tp3_rationale or "", rr3))
        agg_after = user.account.aggregate_open_risk_usd + size.risk_usd
        reason = (
            f"{d.name} v{d.version} {prop.direction}: {len(prop.rules_triggered)} rules triggered, all hard gates passed, "
            f"score {score.score:.0f} >= threshold, {score.independent_families_supporting} independent evidence families, net R:R {rr1:.2f} to TP1"
        )
        return TradeSetup(
            instrument="XAU/USD",
            bid=q.bid,
            ask=q.ask,
            spread=round(q.spread, 2),
            data_provider=snap.provider + (" (DEMO DATA)" if snap.demo_data else ""),
            price_timestamp=q.ts,
            user_timezone=user.timezone,
            horizon=horizon.value,
            strategy_id=s.id,
            strategy_name=d.name,
            strategy_version=d.version,
            direction=prop.direction,
            entry_trigger=prop.entry_trigger,
            entry_zone_low=prop.entry_zone_low,
            entry_zone_high=prop.entry_zone_high,
            entry_reference=prop.entry_reference,
            entry_confirmation_required=prop.confirmation_required,
            entry_confirmed=prop.confirmed,
            stop_loss=prop.stop,
            stop_rationale=prop.stop_rationale,
            targets=targets,
            estimated_spread=round(costs.spread, 2),
            estimated_slippage=round(costs.total_slippage, 2),
            estimated_fees_usd=round(costs.commission_per_lot_usd * size.lots, 2),
            estimated_financing_usd=round(costs.financing_estimate_usd * size.lots, 2),
            expiry=prop.expiry,
            max_holding_until=prop.max_holding_until,
            market_regime=regime.to_dict(),
            news_risk=snap.news.to_dict(user.timezone),
            supporting_evidence=[e.to_dict() for e in score.supporting],
            contradictory_evidence=[e.to_dict() for e in score.contradicting],
            invalidation_conditions=prop.invalidation,
            position_size=size.to_dict(),
            total_account_risk_usd=round(size.risk_usd, 2),
            total_account_risk_pct=round(size.risk_pct, 3),
            aggregate_exposure_after_usd=round(agg_after, 2),
            aggregate_exposure_after_pct=round(agg_after / user.account.equity_usd * 100, 3),
            confidence_low=cal.low,
            confidence_high=cal.high,
            confidence_method=cal.method,
            historical_sample_size=cal.sample_size,
            backtest_approval_status=f"{state.status}: {state.approval_note}" if state.approval_note else state.status,
            data_quality_status="VALID" if all(r.status == DataStatus.VALID for r in snap.candle_reports.values()) else "DEGRADED",
            notification_timestamp=None,
            uncertainty_statement=UNCERTAINTY_STATEMENT,
            evidence_inspector_ref="",
            decision_reason=reason,
            contract_spec_id=user.spec.spec_id,
            demo_data=snap.demo_data,
        )

    # --------------------------------------------------- all horizons ----
    def evaluate_all(self, snap: MarketSnapshot, user: UserContext, strategies_by_horizon: dict[Horizon, list[Strategy]], states: dict[str, StrategyRuntimeState]) -> dict[Horizon, Decision]:
        out: dict[Horizon, Decision] = {}
        for h in Horizon:
            out[h] = self.evaluate_horizon(snap, user, h, strategies_by_horizon.get(h, []), states)
        # cross-horizon conflict detection
        dirs = {h: d.status for h, d in out.items() if d.status in (DecisionStatus.BUY_SETUP, DecisionStatus.SELL_SETUP)}
        if len(set(dirs.values())) > 1:
            for h, d in out.items():
                if d.setup is None:
                    continue
                others = [f"{oh.value}={od.value}" for oh, od in dirs.items() if oh != h and od != d.status]
                if others:
                    d.setup.conflicting_horizons = others
                    d.setup.contradictory_evidence.append({"family": "structure", "key": "horizon_conflict", "direction": -1 if d.status == DecisionStatus.BUY_SETUP else 1, "strength": 0.5, "description": f"opposite direction on other horizon(s): {', '.join(others)}", "source": "decision-engine", "ts": snap.as_of.isoformat(), "correlated_group": None, "available": True})
                    d.evidence_inspector["contradictory"].append(d.setup.contradictory_evidence[-1])
                    d.evidence_inspector["horizon_conflict"] = others
                    d.reason += f"; NOTE conflicting direction on {', '.join(others)} - treat as elevated risk"
        return out
