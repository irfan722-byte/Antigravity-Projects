"""Backtesting engine.

Replays history bar by bar through the *same* strategy, structure, regime,
risk and paper-execution code used live. Protections:
- evaluation at time t only sees candles that closed at or before t (provider
  slices are cut at t and the forming bar is discarded);
- calendar events are fetched "as of" t so actuals are unknown before release;
- fills, spread and slippage come from the paper engine's rules (bid/ask,
  conservative same-bar, gap-through-stop);
- weekend/session logic uses the shared market_state function;
- results carry a config hash and the data label so runs are reproducible and
  never confused with real-market validation.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..core.calibration import calibrated_probability
from ..core.candles import Candle, Timeframe, only_complete
from ..core.contract_spec import ContractSpec
from ..core.decision import ANCHOR_TF, HORIZON_TIMEFRAMES, estimate_slippage
from ..core.evidence import score_evidence
from ..core.news_state import NewsConfig, assess_news_state
from ..core.regime import classify_regime
from ..core.risk import CostModel, RiskLimits, SizeStatus, compute_position_size, net_reward_to_risk
from ..core.setup import Horizon
from ..core.strategies.base import Strategy, StrategyContext
from ..core.structure import StructureParams, analyse_structure
from ..core.timeutil import MarketState, market_state, past_friday_cutoff, session_label
from ..paper.engine import OrderType, PaperEngine, PaperOrder, PositionStatus, SlippageParams
from ..providers.base import CalendarProvider, MarketDataProvider
from .metrics import TradeRecord, compute_metrics

EVAL_TF: dict[str, Timeframe] = {"PBC-H1": Timeframe.H1, "BRT-M15": Timeframe.M15, "RRJ-H4": Timeframe.H4, "PNC-M15": Timeframe.M15}


@dataclass
class BacktestConfig:
    strategy_id: str
    start: datetime
    end: datetime
    starting_equity: float = 10000.0
    risk_pct: float = 0.5
    min_net_rr: float = 1.5
    spread_multiplier: float = 1.0
    slippage_multiplier: float = 1.0
    friday_cutoff_local: str = "20:00"
    user_tz: str = "Asia/Dubai"
    weekly_friday_close: bool = True
    score_threshold: float | None = None  # None => record score but do not filter (research mode)
    params_override: dict = field(default_factory=dict)
    structure_params: StructureParams = field(default_factory=StructureParams)
    label: str = "IN_SAMPLE"
    data_label: str = "DEMO"
    validation_for_calibration: dict | None = None

    def hash(self) -> str:
        d = dict(self.__dict__)
        d["start"], d["end"] = self.start.isoformat(), self.end.isoformat()
        d["structure_params"] = self.structure_params.__dict__
        return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()[:16]


@dataclass
class BacktestResult:
    config_hash: str
    strategy_id: str
    strategy_version: str
    label: str
    data_label: str
    start: datetime
    end: datetime
    trades: list[TradeRecord]
    metrics: dict
    evaluations: int
    proposals: int
    rejected_by_gate: dict[str, int]
    warnings: list[str]
    trades_hash: str

    def to_dict(self) -> dict:
        return {
            "config_hash": self.config_hash,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "label": self.label,
            "data_label": self.data_label,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "evaluations": self.evaluations,
            "proposals": self.proposals,
            "rejected_by_gate": self.rejected_by_gate,
            "warnings": self.warnings,
            "trades_hash": self.trades_hash,
            "metrics": self.metrics,
            "trades": [t.to_dict() for t in self.trades],
        }


class Backtester:
    def __init__(self, market: MarketDataProvider, calendar: CalendarProvider, spec: ContractSpec):
        self.market = market
        self.calendar = calendar
        self.spec = spec

    def _candles_upto(self, tf: Timeframe, t: datetime, bars: int) -> list[Candle]:
        span = timedelta(seconds=bars * tf.seconds * 7 / 5) + timedelta(days=3)
        return only_complete(self.market.get_candles("XAUUSD", tf, t - span, t), t)

    def run(self, strategy: Strategy, cfg: BacktestConfig) -> BacktestResult:
        d = strategy.definition
        horizon = Horizon(d.horizon)
        eval_tf = EVAL_TF.get(strategy.id, Timeframe.H1)
        tfs = HORIZON_TIMEFRAMES[horizon]
        anchor = ANCHOR_TF[horizon]
        warnings = ["Candle-based fills (M1 mid ± spread). Not sufficient for scalp execution modelling.", f"Data label: {cfg.data_label}. Demo data is synthetic and cannot validate a strategy for real use."]
        slip = SlippageParams(0.10 * cfg.slippage_multiplier, 0.10 * cfg.slippage_multiplier, 0.15 * cfg.slippage_multiplier)
        engine = PaperEngine(self.spec, slip, conservative_same_bar=True)
        RiskLimits.defaults()
        equity = cfg.starting_equity
        rejected: dict[str, int] = {}
        trades: list[TradeRecord] = []
        evaluations = 0
        proposals = 0
        params = dict(cfg.params_override)
        events_cache = self.calendar.get_events(cfg.start - timedelta(days=3), cfg.end + timedelta(days=3), cfg.end)
        # point-in-time view of events: strip actuals for events not yet released at t
        from copy import copy

        def events_as_of(t: datetime):
            out = []
            for e in events_cache:
                e2 = copy(e)
                if e2.scheduled_ts + timedelta(seconds=20) > t:
                    e2.actual, e2.published_ts, e2.revised_prior = None, None, None
                    from ..core.news_state import Verification

                    e2.verification = Verification.PENDING
                out.append(e2)
            return out

        # iterate over eval timeframe bar closes
        all_eval = self.market.get_candles("XAUUSD", eval_tf, cfg.start, cfg.end)
        m1_all = self.market.get_candles("XAUUSD", Timeframe.M1, cfg.start, cfg.end)
        m1_all = [c for c in m1_all if c.complete]
        m1_idx = 0
        open_meta: dict[str, dict] = {}
        for bar in all_eval:
            if not bar.complete:
                continue
            t = bar.end_ts
            # advance paper engine through M1 candles up to t
            while m1_idx < len(m1_all) and m1_all[m1_idx].end_ts <= t:
                c = m1_all[m1_idx]
                sp = (c.spread_close or 0.3) * cfg.spread_multiplier
                engine.on_candle(Candle(c.instrument, c.timeframe, c.ts, c.open, c.high, c.low, c.close, c.volume, c.volume_kind, sp, True, c.provider, c.ingested_at, c.provenance_id))
                # fill pending market orders on the candle open (next-bar open discipline)
                if m1_idx + 1 < len(m1_all):
                    nxt = m1_all[m1_idx + 1]
                    from ..core.candles import Quote

                    q = Quote("XAUUSD", nxt.open - sp / 2, nxt.open + sp / 2, nxt.ts, c.provider, nxt.ts)
                    engine.on_quote(q)
                m1_idx += 1
            # harvest closed positions
            for pos in list(engine.positions.values()):
                if pos.status == PositionStatus.CLOSED and pos.position_id not in {tr.trade_id for tr in trades}:
                    meta = open_meta.get(pos.order_id, {})
                    gross = (1 if pos.direction == "BUY" else -1) * (pos.fills[-1].price - pos.entry_price) * pos.lots_initial * self.spec.contract_size_oz
                    trades.append(TradeRecord(pos.position_id, strategy.id, d.version, d.horizon, pos.direction, pos.entry_ts, pos.exit_ts, pos.entry_price, pos.fills[-1].price, pos.lots_initial, pos.risk_usd, round(pos.realised_pnl_usd, 2), round(gross + meta.get("spread_cost", 0.0), 2), round(meta.get("spread_cost", 0.0) + sum(f.slippage * f.lots * self.spec.contract_size_oz for f in pos.fills), 2), pos.exit_reason or "", meta.get("session", ""), meta.get("regime", ""), meta.get("score"), meta.get("near_event", False), " ".join(f.label for f in pos.fills if f.label).strip(), meta.get("calibrated_p")))
                    equity += pos.realised_pnl_usd
            # Friday closure for weekly/swing horizons
            if cfg.weekly_friday_close and horizon in (Horizon.SWING, Horizon.WEEKLY) and past_friday_cutoff(t, cfg.user_tz, cfg.friday_cutoff_local) and engine.open_positions():
                from ..core.candles import Quote

                sp = (bar.spread_close or 0.3) * cfg.spread_multiplier
                engine.close_all(Quote("XAUUSD", bar.close - sp / 2, bar.close + sp / 2, t, bar.provider, t), "friday_close")
            if market_state(t) != MarketState.OPEN:
                continue
            evaluations += 1
            candles = {tf: self._candles_upto(tf, t, 320 if tf.seconds < 86400 else 260) for tf in tfs}
            if any(len(candles[tf]) < 60 for tf in tfs if tf != Timeframe.D1) or len(candles.get(Timeframe.D1, [])) < 30:
                continue
            structures = {}
            for tf, cs in candles.items():
                try:
                    structures[tf] = analyse_structure(cs, t, cfg.structure_params, daily_candles=candles.get(Timeframe.D1))
                except ValueError:
                    pass
            sp = (bar.spread_close or 0.3) * cfg.spread_multiplier
            sess = session_label(t)
            news = assess_news_state(events_as_of(t), t, NewsConfig(), sp, 0.25)
            regime = classify_regime(candles[anchor], structures.get(anchor), structures.get(Timeframe.D1) if anchor != Timeframe.D1 else None, None, news.phase.value, sess, sp, 0.25, t)
            regime_set = {regime.primary.value, *(x.value for x in regime.tags)}
            from ..core.candles import Quote

            q = Quote("XAUUSD", bar.close - sp / 2, bar.close + sp / 2, t, bar.provider, t)
            # gates that the backtest can honour without a user account
            if news.is_lockout:
                rejected["G06"] = rejected.get("G06", 0) + 1
                continue
            if regime.primary.value not in d.approved_regimes or regime_set & set(d.prohibited_regimes):
                rejected["G08"] = rejected.get("G08", 0) + 1
                continue
            if sess not in d.sessions and not any(s in sess for s in d.sessions):
                rejected["G05"] = rejected.get("G05", 0) + 1
                continue
            if sp > d.spread_limit:
                rejected["G03"] = rejected.get("G03", 0) + 1
                continue
            if engine.open_positions() or any(o.status.value in ("PENDING", "PARTIAL") for o in engine.orders.values()):
                continue  # one position at a time per strategy in research runs
            ctx = StrategyContext(t, q, candles, structures, regime, sess, news.phase.value, {}, [], [], [], params, cfg.structure_params, news.reaction)
            prop = strategy.evaluate(ctx)
            if prop is None or prop.developing:
                continue
            proposals += 1
            slippage = estimate_slippage(sp, sess, structures[anchor].volatility if anchor in structures else "NORMAL") * cfg.slippage_multiplier
            costs = CostModel(sp, slippage / 2, slippage / 2, self.spec.commission_per_lot_round_trip_usd)
            size = compute_position_size(equity, cfg.risk_pct, prop.entry_reference, prop.stop, prop.direction, costs, self.spec)
            if size.status != SizeStatus.OK:
                rejected["G14"] = rejected.get("G14", 0) + 1
                continue
            rr1 = net_reward_to_risk(prop.entry_reference, prop.stop, prop.tp1, prop.direction, costs, self.spec)
            if rr1 is None or rr1 < max(cfg.min_net_rr, d.min_net_rr):
                rejected["G13"] = rejected.get("G13", 0) + 1
                continue
            sb = score_evidence(prop.evidence, 1 if prop.direction == "BUY" else -1)
            if cfg.score_threshold is not None and sb.score < cfg.score_threshold:
                rejected["SCORE"] = rejected.get("SCORE", 0) + 1
                continue
            cal = calibrated_probability(cfg.validation_for_calibration, sb.score) if cfg.validation_for_calibration else None
            oid = engine.new_id("ord")
            order = PaperOrder(oid, None, strategy.id, d.version, d.horizon, prop.direction, OrderType.MARKET, size.lots, prop.stop, prop.tp1, prop.tp2, prop.expiry, prop.max_holding_until, d.spread_limit, t, tp3=prop.tp3, partial_close_at_tp1_pct=d.partial_close_at_tp1_pct, move_to_breakeven_after_tp1=d.move_to_breakeven_after_tp1, risk_usd=size.risk_usd)
            engine.submit(order)
            near = news.phase.value != "NONE"
            open_meta[oid] = {"session": sess, "regime": regime.primary.value, "score": sb.score, "near_event": near, "spread_cost": sp * size.lots * self.spec.contract_size_oz, "calibrated_p": cal.point if cal else None}
        # close anything still open at the end at last known price (labelled)
        if engine.open_positions() and m1_all:
            from ..core.candles import Quote

            last = m1_all[-1]
            sp = (last.spread_close or 0.3) * cfg.spread_multiplier
            engine.close_all(Quote("XAUUSD", last.close - sp / 2, last.close + sp / 2, last.end_ts, last.provider, last.end_ts), "end_of_test")
            for pos in engine.positions.values():
                if pos.status == PositionStatus.CLOSED and pos.position_id not in {tr.trade_id for tr in trades}:
                    meta = open_meta.get(pos.order_id, {})
                    gross = (1 if pos.direction == "BUY" else -1) * (pos.fills[-1].price - pos.entry_price) * pos.lots_initial * self.spec.contract_size_oz
                    trades.append(TradeRecord(pos.position_id, strategy.id, d.version, d.horizon, pos.direction, pos.entry_ts, pos.exit_ts, pos.entry_price, pos.fills[-1].price, pos.lots_initial, pos.risk_usd, round(pos.realised_pnl_usd, 2), round(gross + meta.get("spread_cost", 0.0), 2), round(meta.get("spread_cost", 0.0), 2), pos.exit_reason or "", meta.get("session", ""), meta.get("regime", ""), meta.get("score"), meta.get("near_event", False), "END_OF_TEST", meta.get("calibrated_p")))
        period_days = (cfg.end - cfg.start).total_seconds() / 86400
        metrics = compute_metrics(trades, cfg.starting_equity, period_days, cfg.label)
        th = hashlib.sha256(json.dumps([t.to_dict() for t in trades], sort_keys=True).encode()).hexdigest()[:16]
        return BacktestResult(cfg.hash(), strategy.id, d.version, cfg.label, cfg.data_label, cfg.start, cfg.end, trades, metrics, evaluations, proposals, rejected, warnings, th)
