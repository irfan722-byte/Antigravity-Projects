"""RRJ-H4: Range Rejection (swing). RESEARCH status: implemented for backtesting, not approved."""
from __future__ import annotations

from ..candles import Timeframe
from ..evidence import Evidence, Family
from ..regime import Regime
from .base import Strategy, StrategyContext, StrategyProposal
from .common import atr_value


class RangeRejection(Strategy):
    def evaluate(self, ctx: StrategyContext) -> StrategyProposal | None:
        p = self.definition.params | ctx.params
        h4 = ctx.candles.get(Timeframe.H4, [])
        snap = ctx.structures.get(Timeframe.H4)
        if len(h4) < 40 or snap is None or snap.range_state is None or not snap.range_state.is_range:
            return None
        if ctx.regime.primary != Regime.RANGE:
            return None
        a = atr_value(h4, p["atr_period"])
        if not a:
            return None
        rs = snap.range_state
        last = h4[-1]
        # exclude the last bar from the range boundaries so the sweep is measured against prior extremes
        prior = h4[-21:-1]
        hi, lo = max(c.high for c in prior), min(c.low for c in prior)
        mid = (hi + lo) / 2
        if last.range <= 0:
            return None
        upper_wick = last.high - max(last.open, last.close)
        lower_wick = min(last.open, last.close) - last.low
        direction = None
        if last.high >= hi + p["sweep_atr"] * a and last.close < hi and upper_wick / last.range >= 0.6:
            direction, extreme = "SELL", last.high
        elif last.low <= lo - p["sweep_atr"] * a and last.close > lo and lower_wick / last.range >= 0.6:
            direction, extreme = "BUY", last.low
        if direction is None:
            return None
        buf = p["stop_buffer_atr"] * a
        stop = round(extreme + buf, 2) if direction == "SELL" else round(extreme - buf, 2)
        entry_ref = ctx.quote.bid if direction == "SELL" else ctx.quote.ask
        tp1 = round(mid, 2)
        tp2 = round(lo + p["tp2_inset_atr"] * a, 2) if direction == "SELL" else round(hi - p["tp2_inset_atr"] * a, 2)
        ev = [
            Evidence(Family.STRUCTURE, "range_sweep_rejection", -1 if direction == "SELL" else 1, 0.7, f"sweep of range {'high' if direction == 'SELL' else 'low'} with rejection close back inside", "structure:H4", ctx.as_of),
            Evidence(Family.VOLATILITY, "range_width", 0, 0.3, f"range width {rs.width_atr:.1f} ATR", "structure:H4", ctx.as_of),
        ]
        return StrategyProposal(
            direction=direction, entry_type="market", entry_reference=round(entry_ref, 2),
            entry_zone_low=round(last.close - 0.2 * a, 2), entry_zone_high=round(last.close + 0.2 * a, 2),
            entry_trigger=self.definition.entry_trigger, confirmation_required=True, confirmed=True,
            stop=stop, stop_rationale=f"beyond sweep extreme {extreme:.2f} plus {p['stop_buffer_atr']} ATR", tp1=tp1, tp1_rationale="range midpoint",
            tp2=tp2, tp2_rationale="opposite range extreme minus inset", expiry=self.expiry_for(ctx.as_of), max_holding_until=self.max_hold_for(ctx.as_of),
            invalidation=[f"H4 close beyond {extreme:.2f}", "regime leaves RANGE"], evidence=ev,
            rules_triggered=["R1 range regime", "R2 sweep beyond range extreme", "R3 rejection close back inside"], rules_not_triggered=[],
        )
