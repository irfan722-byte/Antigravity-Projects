"""PBC-H1: Pullback Continuation (intraday, H1 anchored, H4 trend context)."""
from __future__ import annotations

from ..candles import Timeframe
from ..evidence import Evidence, Family
from ..structure import Trend, detect_displacement, detect_rejection
from .base import Strategy, StrategyContext, StrategyProposal
from .common import atr_value, ema_pair, levels_from, next_level, ordered_targets, rsi_value


class PullbackContinuation(Strategy):
    def evaluate(self, ctx: StrategyContext) -> StrategyProposal | None:
        p = self.definition.params | ctx.params
        h1 = ctx.candles.get(Timeframe.H1, [])
        if len(h1) < p["ema_slow"] + 5:
            return None
        h4s = ctx.structures.get(Timeframe.H4)
        h1s = ctx.structures.get(Timeframe.H1)
        a = atr_value(h1, p["atr_period"])
        if not a:
            return None
        triggered: list[str] = []
        not_triggered: list[str] = []
        ev: list[Evidence] = []

        # R1 regime + H4 structure agree on direction
        direction = None
        rd = ctx.regime.trend_direction
        if rd == "UP" and h4s and h4s.trend == Trend.UP:
            direction = "BUY"
        elif rd == "DOWN" and h4s and h4s.trend == Trend.DOWN:
            direction = "SELL"
        if direction is None:
            not_triggered.append("R1 regime direction and H4 swing structure agree")
            return None
        triggered.append(f"R1 regime {rd} and H4 structure {h4s.trend.value} agree")
        ev.append(Evidence(Family.STRUCTURE, "h4_swing_structure", 1 if direction == "BUY" else -1, 0.7, f"H4 {h4s.trend.value} (HH/HL or LH/LL)", "structure:H4", ctx.as_of))

        # R2 EMA alignment
        fast, slow = ema_pair(h1, p["ema_fast"], p["ema_slow"])
        if fast is None or slow is None:
            return None
        aligned = fast > slow if direction == "BUY" else fast < slow
        if not aligned:
            not_triggered.append("R2 H1 EMA20 on trend side of EMA50")
            return None
        triggered.append(f"R2 EMA{p['ema_fast']} {fast:.2f} vs EMA{p['ema_slow']} {slow:.2f} aligned {direction}")
        ev.append(Evidence(Family.TECHNICAL, "ema_fast_slow", 1 if direction == "BUY" else -1, min(1.0, abs(fast - slow) / a), "H1 EMA alignment", "indicator:ema", ctx.as_of, correlated_group="trend_ma"))

        # R3 pullback to EMA zone in lookback
        look = h1[-p["pullback_lookback"] :]
        tol = p["pullback_tolerance_atr"] * a
        if direction == "BUY":
            touched = [c for c in look if c.low <= fast + tol]
            extreme = min(c.low for c in look)
        else:
            touched = [c for c in look if c.high >= fast - tol]
            extreme = max(c.high for c in look)
        if not touched:
            not_triggered.append("R3 pullback into EMA20 zone within lookback")
            return None
        triggered.append(f"R3 pullback touched EMA zone ({len(touched)} bars), extreme {extreme:.2f}")
        ev.append(Evidence(Family.STRUCTURE, "pullback_depth", 1 if direction == "BUY" else -1, 0.5, f"pullback extreme {extreme:.2f} vs EMA {fast:.2f}", "structure:H1", ctx.as_of))

        # R4 trigger on last closed bar
        last = h1[-1]
        prev = h1[-2]
        rej = detect_rejection(h1, ctx.structure_params)
        disp = detect_displacement(h1, ctx.structure_params)
        want = "bullish" if direction == "BUY" else "bearish"
        if direction == "BUY":
            side_ok = last.close > fast and last.bullish
            beyond_prev = last.close > prev.high
        else:
            side_ok = last.close < fast and last.bearish
            beyond_prev = last.close < prev.low
        pattern_ok = (rej is not None and rej.direction == want) or (disp is not None and disp.direction == want) or beyond_prev
        confirmed = side_ok and pattern_ok
        if confirmed:
            triggered.append("R4 trigger bar closed on trend side of EMA with rejection/displacement/close beyond prior extreme")
            ev.append(Evidence(Family.TECHNICAL, "trigger_candle", 1 if direction == "BUY" else -1, 0.6, "H1 trigger candle", "structure:H1", ctx.as_of))
        else:
            not_triggered.append("R4 trigger bar (close on trend side + rejection/displacement/close beyond prior extreme)")

        r = rsi_value(h1, p["rsi_period"])
        if r is not None:
            if direction == "BUY":
                ev.append(Evidence(Family.TECHNICAL, "rsi", 1 if 45 <= r <= 70 else (-1 if r > 75 else 0), 0.4, f"RSI {r:.1f}", "indicator:rsi", ctx.as_of, correlated_group="momentum_osc"))
            else:
                ev.append(Evidence(Family.TECHNICAL, "rsi", 1 if 30 <= r <= 55 else (-1 if r < 25 else 0), 0.4, f"RSI {r:.1f}", "indicator:rsi", ctx.as_of, correlated_group="momentum_osc"))
                # note: for SELL, direction +1 here means "supports the proposal"; normalise below
        # normalise RSI evidence sign to bullish/bearish convention
        ev = [e if e.key != "rsi" else Evidence(e.family, e.key, e.direction * (1 if direction == "BUY" else -1), e.strength, e.description, e.source, e.ts, e.correlated_group) for e in ev]

        # levels & prices
        entry_ref = ctx.quote.ask if direction == "BUY" else ctx.quote.bid
        buf = p["stop_buffer_atr"] * a
        stop = round(extreme - buf, 2) if direction == "BUY" else round(extreme + buf, 2)
        risk_dist = abs(entry_ref - stop)
        if risk_dist <= 0:
            return None
        levels = levels_from(h1s) + levels_from(h4s)
        l1 = next_level(levels, entry_ref, direction, p["tp1_min_atr"] * a, p["tp1_max_r"] * risk_dist)
        if l1 is not None:
            tp1, tp1_r = l1.price, f"structural level {l1.name} ({l1.source})"
        else:
            tp1 = entry_ref + p["tp1_fallback_r"] * risk_dist if direction == "BUY" else entry_ref - p["tp1_fallback_r"] * risk_dist
            tp1_r = f"{p['tp1_fallback_r']}x stop distance (no structural level within reach)"
        l2 = next_level(levels, tp1, direction, 0.5 * a, p["tp2_max_r"] * risk_dist - abs(tp1 - entry_ref))
        if l2 is not None:
            tp2, tp2_r = l2.price, f"next structural level {l2.name} ({l2.source})"
        else:
            tp2 = entry_ref + p["tp2_fallback_r"] * risk_dist if direction == "BUY" else entry_ref - p["tp2_fallback_r"] * risk_dist
            tp2_r = f"{p['tp2_fallback_r']}x stop distance"
        tp1, tp2, replaced = ordered_targets(entry_ref, direction, risk_dist, tp1, tp2, p["tp2_fallback_r"])
        if replaced:
            tp2_r = f"{p['tp2_fallback_r']}x stop distance (structural level not usable)"
        zone_lo, zone_hi = round(last.close - 0.15 * a, 2), round(last.close + 0.15 * a, 2)
        return StrategyProposal(
            direction=direction,
            entry_type="market",
            entry_reference=round(entry_ref, 2),
            entry_zone_low=zone_lo,
            entry_zone_high=zone_hi,
            entry_trigger=self.definition.entry_trigger,
            confirmation_required=True,
            confirmed=confirmed,
            stop=stop,
            stop_rationale=f"{'below' if direction == 'BUY' else 'above'} pullback extreme {extreme:.2f} plus {p['stop_buffer_atr']} ATR buffer ({buf:.2f}); ATR(14,H1)={a:.2f}",
            tp1=round(tp1, 2),
            tp1_rationale=tp1_r,
            tp2=round(tp2, 2),
            tp2_rationale=tp2_r,
            expiry=self.expiry_for(ctx.as_of),
            max_holding_until=self.max_hold_for(ctx.as_of),
            invalidation=[
                f"H1 close {'below' if direction == 'BUY' else 'above'} {extreme:.2f} before entry",
                "regime changes to RANGE, MIXED or UNKNOWN",
                f"setup expiry {self.expiry_for(ctx.as_of).isoformat()}",
                "high-importance USD event enters its pre-event window",
            ],
            evidence=ev,
            rules_triggered=triggered,
            rules_not_triggered=not_triggered,
            developing=not confirmed,
        )
