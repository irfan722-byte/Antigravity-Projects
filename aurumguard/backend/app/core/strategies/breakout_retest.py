"""BRT-M15: Breakout and Retest of previous-day / session levels."""
from __future__ import annotations

from ..candles import Timeframe
from ..evidence import Evidence, Family
from .base import Strategy, StrategyContext, StrategyProposal
from .common import atr_value, levels_from, next_level, ordered_targets

LEVEL_SOURCES = ("PDH", "PDL", "PWH", "PWL", "session_high:ASIA", "session_low:ASIA", "session_high:LONDON", "session_low:LONDON")


class BreakoutRetest(Strategy):
    def evaluate(self, ctx: StrategyContext) -> StrategyProposal | None:
        p = self.definition.params | ctx.params
        m15 = ctx.candles.get(Timeframe.M15, [])
        if len(m15) < p["break_lookback"] + p["atr_period"] + 2:
            return None
        snap = ctx.structures.get(Timeframe.M15)
        a = atr_value(m15, p["atr_period"])
        if not a or snap is None:
            return None
        levels = [l for l in snap.levels if l.source in LEVEL_SOURCES]
        if not levels:
            return None
        look = m15[-p["break_lookback"] :]
        best = None
        for lvl in levels:
            for j, bar in enumerate(look):
                is_disp = bar.range >= p["displacement_atr_mult"] * a and bar.range > 0 and bar.body / bar.range >= 0.6
                if not is_disp:
                    continue
                if bar.close > lvl.price and bar.open <= lvl.price:
                    best = ("BUY", lvl, j, bar)
                elif bar.close < lvl.price and bar.open >= lvl.price:
                    best = ("SELL", lvl, j, bar)
        if best is None:
            return None
        direction, lvl, j, bbar = best
        after = look[j + 1 :]
        triggered = [f"R1 displacement break of {lvl.name} {lvl.price:.2f} at {bbar.ts.isoformat()} (range {bbar.range / a:.1f} ATR)"]
        not_triggered: list[str] = []
        ev = [Evidence(Family.STRUCTURE, "displacement_break", 1 if direction == "BUY" else -1, 0.7, triggered[0], "structure:M15", ctx.as_of)]
        hold_tol = p["hold_tolerance_atr"] * a
        held = all((c.close >= lvl.price - hold_tol) if direction == "BUY" else (c.close <= lvl.price + hold_tol) for c in after)
        if not held:
            not_triggered.append("R2 no close back across the level after the break")
            return None
        triggered.append("R2 level held: no close back across it since the break")
        ret_tol = p["retest_tolerance_atr"] * a
        retested = any((c.low <= lvl.price + ret_tol) if direction == "BUY" else (c.high >= lvl.price - ret_tol) for c in after)
        last = m15[-1]
        if direction == "BUY":
            trig = retested and last.close > lvl.price and last.bullish
            extreme = min([c.low for c in after] or [lvl.price])
        else:
            trig = retested and last.close < lvl.price and last.bearish
            extreme = max([c.high for c in after] or [lvl.price])
        if retested:
            triggered.append("R3a retest touched the level zone")
        else:
            not_triggered.append("R3a retest touch of the level zone")
        if trig:
            triggered.append("R3b trigger bar closed away from the level in the breakout direction")
            ev.append(Evidence(Family.STRUCTURE, "retest_hold", 1 if direction == "BUY" else -1, 0.6, f"retest of {lvl.name} held, extreme {extreme:.2f}", "structure:M15", ctx.as_of))
        else:
            not_triggered.append("R3b trigger bar closing away from the level")
        buf = p["stop_buffer_atr"] * a
        entry_ref = ctx.quote.ask if direction == "BUY" else ctx.quote.bid
        stop = round(min(extreme, lvl.price) - buf, 2) if direction == "BUY" else round(max(extreme, lvl.price) + buf, 2)
        risk_dist = abs(entry_ref - stop)
        if risk_dist <= 0:
            return None
        measured = lvl.price + bbar.range if direction == "BUY" else lvl.price - bbar.range
        floor_tp1 = entry_ref + p["tp1_floor_r"] * risk_dist if direction == "BUY" else entry_ref - p["tp1_floor_r"] * risk_dist
        tp1 = max(measured, floor_tp1) if direction == "BUY" else min(measured, floor_tp1)
        tp1_r = f"measured move (level + breakout bar range {bbar.range:.2f}) floored at {p['tp1_floor_r']}R"
        all_levels = levels_from(snap) + levels_from(ctx.structures.get(Timeframe.H1))
        l2 = next_level(all_levels, tp1, direction, 0.5 * a, p["tp2_max_r"] * risk_dist - abs(tp1 - entry_ref))
        if l2 is not None:
            tp2, tp2_r = l2.price, f"next structural level {l2.name} ({l2.source})"
        else:
            tp2 = entry_ref + p["tp2_fallback_r"] * risk_dist if direction == "BUY" else entry_ref - p["tp2_fallback_r"] * risk_dist
            tp2_r = f"{p['tp2_fallback_r']}x stop distance"
        tp1 = min(tp1, entry_ref + p["tp1_max_r"] * risk_dist) if direction == "BUY" else max(tp1, entry_ref - p["tp1_max_r"] * risk_dist)
        tp1, tp2, replaced = ordered_targets(entry_ref, direction, risk_dist, tp1, tp2, p["tp2_fallback_r"])
        if replaced:
            tp2_r = f"{p['tp2_fallback_r']}x stop distance (structural level not usable)"
        return StrategyProposal(
            direction=direction,
            entry_type="market",
            entry_reference=round(entry_ref, 2),
            entry_zone_low=round(lvl.price - 0.1 * a, 2) if direction == "BUY" else round(lvl.price - ret_tol, 2),
            entry_zone_high=round(lvl.price + ret_tol, 2) if direction == "BUY" else round(lvl.price + 0.1 * a, 2),
            entry_trigger=self.definition.entry_trigger,
            confirmation_required=True,
            confirmed=trig,
            stop=stop,
            stop_rationale=f"beyond retest extreme {extreme:.2f}/level {lvl.price:.2f} plus {p['stop_buffer_atr']} ATR ({buf:.2f}); ATR(14,M15)={a:.2f}",
            tp1=round(tp1, 2),
            tp1_rationale=tp1_r,
            tp2=round(tp2, 2),
            tp2_rationale=tp2_r,
            expiry=self.expiry_for(ctx.as_of),
            max_holding_until=self.max_hold_for(ctx.as_of),
            invalidation=[f"any M15 close back {'below' if direction == 'BUY' else 'above'} {lvl.price:.2f}", "no retest within 8 bars of the break", f"expiry {self.expiry_for(ctx.as_of).isoformat()}", "event pre-window"],
            evidence=ev,
            rules_triggered=triggered,
            rules_not_triggered=not_triggered,
            developing=not trig,
        )
