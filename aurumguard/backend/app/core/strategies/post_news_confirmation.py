"""PNC-M15: Post-News Confirmation. RESEARCH status. Only evaluates in the POST_RELEASE_CONFIRMATION phase."""
from __future__ import annotations

from ..candles import Timeframe
from ..evidence import Evidence, Family
from ..structure import break_of_structure, find_swings
from .base import Strategy, StrategyContext, StrategyProposal
from .common import atr_value, levels_from, next_level, ordered_targets


class PostNewsConfirmation(Strategy):
    def evaluate(self, ctx: StrategyContext) -> StrategyProposal | None:
        p = self.definition.params | ctx.params
        if ctx.news_phase != "POST_RELEASE_CONFIRMATION" or not ctx.latest_event_reaction:
            return None
        rx = ctx.latest_event_reaction
        z = rx.get("standardised_surprise")
        if z is None or abs(z) < p["min_abs_surprise_z"]:
            return None
        # A hawkish (USD-positive) surprise is expected to weigh on gold.
        usd_positive = (z > 0) == bool(rx.get("higher_is_usd_positive", True))
        direction = "SELL" if usd_positive else "BUY"
        dxy_ok = rx.get("dxy_response_sign") == (1 if usd_positive else -1)
        gold_ok = rx.get("gold_response_sign") == (-1 if direction == "SELL" else 1)
        m15 = ctx.candles.get(Timeframe.M15, [])
        if len(m15) < 30:
            return None
        a = atr_value(m15, p["atr_period"])
        if not a:
            return None
        bos = break_of_structure(m15, find_swings(m15, ctx.structure_params), ctx.structure_params)
        bos_ok = bos is not None and bos.direction == ("bearish" if direction == "SELL" else "bullish")
        triggered = [f"R1 standardised surprise {z:+.2f} (USD {'positive' if usd_positive else 'negative'})"]
        not_triggered = []
        (triggered if dxy_ok else not_triggered).append("R2 DXY response confirms")
        (triggered if gold_ok else not_triggered).append("R3 gold response confirms")
        (triggered if bos_ok else not_triggered).append("R4 M15 break of structure in direction")
        ev = [
            Evidence(Family.NEWS_EVENT, "surprise_z", -1 if usd_positive else 1, min(1.0, abs(z) / 2), f"{rx.get('event_name')} surprise z={z:+.2f}", "calendar", ctx.as_of),
            Evidence(Family.INTERMARKET, "dxy_response", (-1 if usd_positive else 1) if dxy_ok else 0, 0.6, "DXY post-release response", "intermarket", ctx.as_of, correlated_group="dollar"),
        ]
        if not (dxy_ok and gold_ok):
            return None
        confirmed = bos_ok
        entry_ref = ctx.quote.bid if direction == "SELL" else ctx.quote.ask
        post_bars = [c for c in m15 if c.ts >= rx["release_ts"]] or m15[-4:]
        extreme = max(c.high for c in post_bars) if direction == "SELL" else min(c.low for c in post_bars)
        buf = p["stop_buffer_atr"] * a
        stop = round(extreme + buf, 2) if direction == "SELL" else round(extreme - buf, 2)
        risk = abs(entry_ref - stop)
        if risk <= 0:
            return None
        tp1 = entry_ref - p["tp1_r"] * risk if direction == "SELL" else entry_ref + p["tp1_r"] * risk
        l2 = next_level(levels_from(ctx.structures.get(Timeframe.M15)), tp1, direction, 0.5 * a, p["tp2_max_r"] * risk - abs(tp1 - entry_ref))
        tp2 = l2.price if l2 else (entry_ref - p["tp2_fallback_r"] * risk if direction == "SELL" else entry_ref + p["tp2_fallback_r"] * risk)
        tp1, tp2, _ = ordered_targets(entry_ref, direction, risk, tp1, tp2, p["tp2_fallback_r"])
        return StrategyProposal(
            direction=direction, entry_type="market", entry_reference=round(entry_ref, 2), entry_zone_low=round(m15[-1].close - 0.15 * a, 2), entry_zone_high=round(m15[-1].close + 0.15 * a, 2),
            entry_trigger=self.definition.entry_trigger, confirmation_required=True, confirmed=confirmed, stop=stop,
            stop_rationale=f"beyond post-release extreme {extreme:.2f} plus {p['stop_buffer_atr']} ATR", tp1=round(tp1, 2), tp1_rationale=f"{p['tp1_r']}R", tp2=round(tp2, 2),
            tp2_rationale="next structural level or fallback R multiple", expiry=self.expiry_for(ctx.as_of), max_holding_until=self.max_hold_for(ctx.as_of),
            invalidation=["M15 close back through the release-bar midpoint", "conflicting components in the release"], evidence=ev, rules_triggered=triggered, rules_not_triggered=not_triggered, developing=not confirmed,
        )
