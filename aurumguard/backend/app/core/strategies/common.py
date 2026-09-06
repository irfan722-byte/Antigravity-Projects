"""Shared helpers for strategy implementations."""
from __future__ import annotations

from typing import Sequence

from ..candles import Candle
from ..indicators import atr, closes, ema, highs, last_valid, lows, rsi
from ..structure import Level, StructureSnapshot


def atr_value(cs: Sequence[Candle], period: int) -> float | None:
    if len(cs) < period + 1:
        return None
    return last_valid(atr(highs(cs), lows(cs), closes(cs), period))


def ema_pair(cs: Sequence[Candle], fast: int, slow: int) -> tuple[float | None, float | None]:
    c = closes(cs)
    return last_valid(ema(c, fast)), last_valid(ema(c, slow))


def rsi_value(cs: Sequence[Candle], period: int) -> float | None:
    return last_valid(rsi(closes(cs), period))


def next_level(levels: Sequence[Level], price: float, direction: str, min_distance: float, max_distance: float | None = None) -> Level | None:
    """Nearest level at least min_distance (and at most max_distance) beyond price in the trade direction."""
    if direction == "BUY":
        cands = [l for l in levels if l.price >= price + min_distance and (max_distance is None or l.price <= price + max_distance)]
        return min(cands, key=lambda l: l.price) if cands else None
    cands = [l for l in levels if l.price <= price - min_distance and (max_distance is None or l.price >= price - max_distance)]
    return max(cands, key=lambda l: l.price) if cands else None


def ordered_targets(entry: float, direction: str, risk_dist: float, tp1: float, tp2: float, tp2_fallback_r: float) -> tuple[float, float, bool]:
    """Guarantee entry < tp1 < tp2 (BUY) or entry > tp1 > tp2 (SELL). Returns (tp1, tp2, tp2_was_replaced)."""
    sign = 1 if direction == "BUY" else -1
    replaced = False
    if sign * (tp2 - tp1) <= 0:
        tp2 = max(entry + sign * tp2_fallback_r * risk_dist, tp1 + sign * 0.5 * risk_dist) if sign > 0 else min(entry + sign * tp2_fallback_r * risk_dist, tp1 + sign * 0.5 * risk_dist)
        replaced = True
    return round(tp1, 2), round(tp2, 2), replaced


def clamp_zone(ref: float, half_width: float) -> tuple[float, float]:
    return round(ref - half_width, 2), round(ref + half_width, 2)


def levels_from(snap: StructureSnapshot | None) -> list[Level]:
    return list(snap.levels) if snap else []
