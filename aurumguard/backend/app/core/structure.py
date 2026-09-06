"""Objective market-structure definitions.

Every concept here has a mathematical definition, explicit parameters with an
allowed range, and a deterministic output. Definitions are documented in
docs/13-strategy-format.md (Market-structure glossary) and unit-tested in
tests/test_structure.py. Nothing here looks at candles after the evaluation
index: all functions operate on a closed-candle list and treat the last element
as the most recent completed bar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Sequence

from .candles import Candle, Timeframe
from .indicators import atr, closes, highs, last_valid, lows
from .timeutil import NY, Session, ensure_utc, session_bounds_utc


@dataclass(frozen=True)
class StructureParams:
    """All parameters with their allowed ranges (validated in __post_init__)."""

    swing_left: int = 3          # bars to the left that must be lower (high) / higher (low). range 2..10
    swing_right: int = 3         # bars to the right. range 1..10
    equal_level_atr_frac: float = 0.10  # tolerance for "equal" highs/lows as a fraction of ATR. range 0.02..0.3
    breakout_close_atr_frac: float = 0.10  # close beyond level by this * ATR to count as a break. range 0.0..0.5
    re_entry_max_bars: int = 3   # bars within which a break that returns inside the range is a failed breakout. range 1..10
    sweep_wick_atr_frac: float = 0.20  # wick beyond level then close back inside: minimum wick excursion in ATR. range 0.05..1.0
    displacement_atr_mult: float = 1.5  # candle range >= this * ATR with body >= 60% of range. range 1.0..3.0
    displacement_body_frac: float = 0.6
    fvg_min_atr_frac: float = 0.10  # minimum gap size as ATR fraction. range 0.0..0.5
    range_lookback: int = 20     # bars for consolidation detection. range 10..100
    range_max_width_atr: float = 3.0  # consolidation if (high-low of lookback) <= this * ATR. range 1..6
    vol_expansion_ratio: float = 1.5  # current ATR / ATR n bars ago. range 1.1..3
    vol_contraction_ratio: float = 0.7
    vol_compare_lookback: int = 10
    atr_period: int = 14
    rejection_wick_frac: float = 0.6  # wick >= 60% of range. range 0.4..0.9

    def __post_init__(self) -> None:
        checks = [
            (2 <= self.swing_left <= 10, "swing_left 2..10"),
            (1 <= self.swing_right <= 10, "swing_right 1..10"),
            (0.02 <= self.equal_level_atr_frac <= 0.3, "equal_level_atr_frac 0.02..0.3"),
            (0.0 <= self.breakout_close_atr_frac <= 0.5, "breakout_close_atr_frac 0..0.5"),
            (1 <= self.re_entry_max_bars <= 10, "re_entry_max_bars 1..10"),
            (0.05 <= self.sweep_wick_atr_frac <= 1.0, "sweep_wick_atr_frac 0.05..1"),
            (1.0 <= self.displacement_atr_mult <= 3.0, "displacement_atr_mult 1..3"),
            (0.0 <= self.fvg_min_atr_frac <= 0.5, "fvg_min_atr_frac 0..0.5"),
            (10 <= self.range_lookback <= 100, "range_lookback 10..100"),
            (1.0 <= self.range_max_width_atr <= 6.0, "range_max_width_atr 1..6"),
            (1.1 <= self.vol_expansion_ratio <= 3.0, "vol_expansion_ratio 1.1..3"),
            (0.4 <= self.rejection_wick_frac <= 0.9, "rejection_wick_frac 0.4..0.9"),
        ]
        for ok, msg in checks:
            if not ok:
                raise ValueError(f"StructureParams out of allowed range: {msg}")


class SwingKind(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


@dataclass(frozen=True)
class Swing:
    kind: SwingKind
    index: int
    ts: datetime
    price: float


class Trend(str, Enum):
    UP = "UP"        # last two swing highs and lows are HH/HL
    DOWN = "DOWN"    # LH/LL
    SIDEWAYS = "SIDEWAYS"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Level:
    name: str
    price: float
    kind: str  # "resistance" | "support" | "pivot"
    source: str  # e.g. "PDH", "PWL", "swing_high", "session_high:LONDON"


@dataclass
class StructureEvent:
    """A detected, labelled pattern. Labels are deliberately non-conspiratorial."""

    kind: str
    direction: str  # "bullish" | "bearish" | "neutral"
    index: int
    ts: datetime
    level: float | None
    label: str  # "Observed liquidity pattern" | "Possible failed breakout" | "Possible stop-run-like behaviour" | "Confirmed strategy condition"
    detail: str = ""
    params: dict = field(default_factory=dict)


# ----------------------------------------------------------------- swings --

def find_swings(candles: Sequence[Candle], p: StructureParams = StructureParams()) -> list[Swing]:
    """Fractal swings. Swing high at i: high[i] > every high in [i-L, i) and >= every high in (i, i+R].

    Confirmation rule: a swing is only known R bars after it forms. It is
    therefore attributed to index i but only *available* from index i+R.
    """
    n = len(candles)
    out: list[Swing] = []
    L, R = p.swing_left, p.swing_right
    for i in range(L, n - R):
        h = candles[i].high
        l = candles[i].low
        if all(candles[j].high < h for j in range(i - L, i)) and all(candles[j].high <= h for j in range(i + 1, i + R + 1)):
            out.append(Swing(SwingKind.HIGH, i, candles[i].ts, h))
        if all(candles[j].low > l for j in range(i - L, i)) and all(candles[j].low >= l for j in range(i + 1, i + R + 1)):
            out.append(Swing(SwingKind.LOW, i, candles[i].ts, l))
    return out


def classify_trend(swings: Sequence[Swing]) -> Trend:
    hs = [s for s in swings if s.kind == SwingKind.HIGH][-2:]
    ls = [s for s in swings if s.kind == SwingKind.LOW][-2:]
    if len(hs) < 2 or len(ls) < 2:
        return Trend.UNKNOWN
    hh = hs[1].price > hs[0].price
    hl = ls[1].price > ls[0].price
    lh = hs[1].price < hs[0].price
    ll = ls[1].price < ls[0].price
    if hh and hl:
        return Trend.UP
    if lh and ll:
        return Trend.DOWN
    return Trend.SIDEWAYS


def _atr_now(candles: Sequence[Candle], period: int, cached: float | None = None) -> float | None:
    """ATR(period) on the most recent bars. Uses a bounded window (8 x period) so repeated
    calls stay cheap; the Wilder warm-up difference versus a full-history ATR is negligible
    at that window and identical between live and backtest use."""
    if cached is not None:
        return cached
    if len(candles) < period + 1:
        return None
    win = candles[-(period * 8) :]
    return last_valid(atr(highs(win), lows(win), closes(win), period))


# ------------------------------------------------------- break of structure --

def break_of_structure(candles: Sequence[Candle], swings: Sequence[Swing], p: StructureParams = StructureParams(), atr_value: float | None = None) -> StructureEvent | None:
    """BOS: last closed candle closes beyond the most recent confirmed swing high (bullish) or low (bearish)
    by at least breakout_close_atr_frac * ATR. Market-structure shift (MSS) = BOS against the prior trend.
    """
    a = _atr_now(candles, p.atr_period, atr_value)
    if a is None or not swings:
        return None
    i = len(candles) - 1
    c = candles[i]
    trend = classify_trend(swings)
    hs = [s for s in swings if s.kind == SwingKind.HIGH and s.index + p.swing_right <= i]
    ls = [s for s in swings if s.kind == SwingKind.LOW and s.index + p.swing_right <= i]
    thr = p.breakout_close_atr_frac * a
    if hs and c.close > hs[-1].price + thr:
        kind = "MSS" if trend == Trend.DOWN else "BOS"
        return StructureEvent(kind, "bullish", i, c.ts, hs[-1].price, "Confirmed strategy condition", f"close {c.close:.2f} above swing high {hs[-1].price:.2f}")
    if ls and c.close < ls[-1].price - thr:
        kind = "MSS" if trend == Trend.UP else "BOS"
        return StructureEvent(kind, "bearish", i, c.ts, ls[-1].price, "Confirmed strategy condition", f"close {c.close:.2f} below swing low {ls[-1].price:.2f}")
    return None


# ------------------------------------------------------------------ levels --

def previous_period_levels(candles: Sequence[Candle], as_of: datetime) -> list[Level]:
    """Previous day/week/month high & low from candles closed before as_of (NY calendar days)."""
    as_of = ensure_utc(as_of)
    local_now = as_of.astimezone(NY)
    out: list[Level] = []
    by_day: dict[date, list[Candle]] = {}
    for c in candles:
        if c.end_ts > as_of:
            continue
        d = c.ts.astimezone(NY).date()
        by_day.setdefault(d, []).append(c)
    days = sorted(d for d in by_day if d < local_now.date())
    if days:
        pd = by_day[days[-1]]
        out.append(Level("PDH", max(c.high for c in pd), "resistance", "PDH"))
        out.append(Level("PDL", min(c.low for c in pd), "support", "PDL"))
    this_week = local_now.isocalendar()[:2]
    prev_week_days = [d for d in days if d.isocalendar()[:2] != this_week]
    if prev_week_days:
        target = prev_week_days[-1].isocalendar()[:2]
        wk = [c for d in prev_week_days if d.isocalendar()[:2] == target for c in by_day[d]]
        out.append(Level("PWH", max(c.high for c in wk), "resistance", "PWH"))
        out.append(Level("PWL", min(c.low for c in wk), "support", "PWL"))
    prev_month_days = [d for d in days if (d.year, d.month) != (local_now.year, local_now.month)]
    if prev_month_days:
        target_m = (prev_month_days[-1].year, prev_month_days[-1].month)
        mo = [c for d in prev_month_days if (d.year, d.month) == target_m for c in by_day[d]]
        out.append(Level("PMH", max(c.high for c in mo), "resistance", "PMH"))
        out.append(Level("PML", min(c.low for c in mo), "support", "PML"))
    return out


def session_levels(candles: Sequence[Candle], as_of: datetime) -> list[Level]:
    """Today's Asia/London/NY session highs and lows (completed portions only)."""
    as_of = ensure_utc(as_of)
    out: list[Level] = []
    for s in Session:
        for day_offset in (0, -1):
            d = (as_of + timedelta(days=day_offset)).astimezone(NY).date()
            start, end = session_bounds_utc(s, d)
            if start > as_of:
                continue
            members = [c for c in candles if start <= c.ts < end and c.end_ts <= as_of]
            if not members:
                continue
            out.append(Level(f"{s.value}_HIGH", max(c.high for c in members), "resistance", f"session_high:{s.value}"))
            out.append(Level(f"{s.value}_LOW", min(c.low for c in members), "support", f"session_low:{s.value}"))
            break
    return out


def swing_levels(swings: Sequence[Swing], n: int = 3) -> list[Level]:
    hs = [s for s in swings if s.kind == SwingKind.HIGH][-n:]
    ls = [s for s in swings if s.kind == SwingKind.LOW][-n:]
    return [Level(f"SH@{s.price:.2f}", s.price, "resistance", "swing_high") for s in hs] + [
        Level(f"SL@{s.price:.2f}", s.price, "support", "swing_low") for s in ls
    ]


def equal_levels(swings: Sequence[Swing], atr_value: float, p: StructureParams = StructureParams()) -> list[StructureEvent]:
    """Equal highs/lows: two consecutive swings of the same kind within equal_level_atr_frac*ATR."""
    out: list[StructureEvent] = []
    tol = p.equal_level_atr_frac * atr_value
    for kind in (SwingKind.HIGH, SwingKind.LOW):
        ss = [s for s in swings if s.kind == kind]
        for a, b in zip(ss, ss[1:]):
            if abs(a.price - b.price) <= tol:
                out.append(StructureEvent(f"EQUAL_{kind.value}S", "neutral", b.index, b.ts, (a.price + b.price) / 2, "Observed liquidity pattern", f"{kind.value.lower()}s at {a.price:.2f}/{b.price:.2f} within {tol:.2f}"))
    return out


# ------------------------------------------------------------ range / vol --

@dataclass(frozen=True)
class RangeState:
    is_range: bool
    high: float
    low: float
    width_atr: float


def consolidation_range(candles: Sequence[Candle], p: StructureParams = StructureParams(), atr_value: float | None = None) -> RangeState | None:
    a = _atr_now(candles, p.atr_period, atr_value)
    if a is None or len(candles) < p.range_lookback:
        return None
    win = candles[-p.range_lookback :]
    hi, lo = max(c.high for c in win), min(c.low for c in win)
    w = (hi - lo) / a if a else float("inf")
    return RangeState(w <= p.range_max_width_atr, hi, lo, w)


def volatility_state(candles: Sequence[Candle], p: StructureParams = StructureParams()) -> str:
    """'EXPANSION' | 'CONTRACTION' | 'NORMAL' | 'UNKNOWN' from ATR now vs ATR vol_compare_lookback bars ago."""
    n = p.atr_period + p.vol_compare_lookback + 1
    if len(candles) < n:
        return "UNKNOWN"
    win = candles[-(p.atr_period * 8 + p.vol_compare_lookback) :]
    a = atr(highs(win), lows(win), closes(win), p.atr_period)
    now, then = a[-1], a[-1 - p.vol_compare_lookback]
    if not (now == now and then == then) or then == 0:
        return "UNKNOWN"
    r = now / then
    if r >= p.vol_expansion_ratio:
        return "EXPANSION"
    if r <= p.vol_contraction_ratio:
        return "CONTRACTION"
    return "NORMAL"


# --------------------------------------------------- breakout / sweep etc --

def detect_breakout(candles: Sequence[Candle], level: Level, p: StructureParams = StructureParams(), atr_value: float | None = None) -> StructureEvent | None:
    """Breakout: last close beyond level by breakout_close_atr_frac*ATR in the direction implied by the level kind."""
    a = _atr_now(candles, p.atr_period, atr_value)
    if a is None:
        return None
    i = len(candles) - 1
    c = candles[i]
    thr = p.breakout_close_atr_frac * a
    if c.close > level.price + thr and c.low <= level.price + a:
        return StructureEvent("BREAKOUT", "bullish", i, c.ts, level.price, "Confirmed strategy condition", f"close above {level.name} {level.price:.2f}")
    if c.close < level.price - thr and c.high >= level.price - a:
        return StructureEvent("BREAKOUT", "bearish", i, c.ts, level.price, "Confirmed strategy condition", f"close below {level.name} {level.price:.2f}")
    return None


def detect_failed_breakout(candles: Sequence[Candle], level: Level, p: StructureParams = StructureParams(), atr_value: float | None = None) -> StructureEvent | None:
    """Failed breakout: within the last re_entry_max_bars+1 bars, a close beyond the level
    followed by a close back on the original side. Labelled 'Possible failed breakout'."""
    a = _atr_now(candles, p.atr_period, atr_value)
    if a is None or len(candles) < p.re_entry_max_bars + 2:
        return None
    thr = p.breakout_close_atr_frac * a
    i = len(candles) - 1
    last = candles[i]
    window = candles[i - p.re_entry_max_bars : i]
    if any(c.close > level.price + thr for c in window) and last.close < level.price:
        return StructureEvent("FAILED_BREAKOUT", "bearish", i, last.ts, level.price, "Possible failed breakout", f"break above {level.name} then close back below within {p.re_entry_max_bars} bars")
    if any(c.close < level.price - thr for c in window) and last.close > level.price:
        return StructureEvent("FAILED_BREAKDOWN", "bullish", i, last.ts, level.price, "Possible failed breakout", f"break below {level.name} then close back above within {p.re_entry_max_bars} bars")
    return None


def detect_sweep(candles: Sequence[Candle], level: Level, p: StructureParams = StructureParams(), atr_value: float | None = None) -> StructureEvent | None:
    """Liquidity sweep: wick beyond level by >= sweep_wick_atr_frac*ATR, close back inside on the same bar."""
    a = _atr_now(candles, p.atr_period, atr_value)
    if a is None:
        return None
    i = len(candles) - 1
    c = candles[i]
    exc = p.sweep_wick_atr_frac * a
    if c.high >= level.price + exc and c.close < level.price:
        return StructureEvent("SWEEP_HIGH", "bearish", i, c.ts, level.price, "Possible stop-run-like behaviour", f"wick {c.high:.2f} above {level.name} {level.price:.2f}, close {c.close:.2f} back inside")
    if c.low <= level.price - exc and c.close > level.price:
        return StructureEvent("SWEEP_LOW", "bullish", i, c.ts, level.price, "Possible stop-run-like behaviour", f"wick {c.low:.2f} below {level.name} {level.price:.2f}, close {c.close:.2f} back inside")
    return None


def detect_displacement(candles: Sequence[Candle], p: StructureParams = StructureParams(), atr_value: float | None = None) -> StructureEvent | None:
    a = _atr_now(candles, p.atr_period, atr_value)
    if a is None:
        return None
    i = len(candles) - 1
    c = candles[i]
    if c.range >= p.displacement_atr_mult * a and c.range > 0 and c.body / c.range >= p.displacement_body_frac:
        return StructureEvent("DISPLACEMENT", "bullish" if c.bullish else "bearish", i, c.ts, None, "Confirmed strategy condition", f"range {c.range:.2f} = {c.range / a:.1f}x ATR, body {c.body / c.range:.0%}")
    return None


def detect_fvg(candles: Sequence[Candle], p: StructureParams = StructureParams(), atr_value: float | None = None) -> StructureEvent | None:
    """Fair-value gap / imbalance on the last three closed bars: low[i] > high[i-2] (bullish) or high[i] < low[i-2]."""
    a = _atr_now(candles, p.atr_period, atr_value)
    if a is None or len(candles) < 3:
        return None
    i = len(candles) - 1
    c0, c2 = candles[i - 2], candles[i]
    if c2.low - c0.high >= p.fvg_min_atr_frac * a:
        return StructureEvent("FVG", "bullish", i, c2.ts, (c2.low + c0.high) / 2, "Observed liquidity pattern", f"gap {c0.high:.2f}-{c2.low:.2f}")
    if c0.low - c2.high >= p.fvg_min_atr_frac * a:
        return StructureEvent("FVG", "bearish", i, c2.ts, (c0.low + c2.high) / 2, "Observed liquidity pattern", f"gap {c2.high:.2f}-{c0.low:.2f}")
    return None


def detect_rejection(candles: Sequence[Candle], p: StructureParams = StructureParams()) -> StructureEvent | None:
    """Rejection candle: dominant wick >= rejection_wick_frac of range."""
    i = len(candles) - 1
    c = candles[i]
    if c.range <= 0:
        return None
    upper = c.high - max(c.open, c.close)
    lower = min(c.open, c.close) - c.low
    if upper / c.range >= p.rejection_wick_frac:
        return StructureEvent("REJECTION", "bearish", i, c.ts, c.high, "Observed liquidity pattern", f"upper wick {upper / c.range:.0%} of range")
    if lower / c.range >= p.rejection_wick_frac:
        return StructureEvent("REJECTION", "bullish", i, c.ts, c.low, "Observed liquidity pattern", f"lower wick {lower / c.range:.0%} of range")
    return None


def detect_gap(candles: Sequence[Candle], p: StructureParams = StructureParams(), atr_value: float | None = None) -> StructureEvent | None:
    """Opening gap between consecutive closed bars larger than fvg_min_atr_frac*ATR (weekend gaps etc.)."""
    a = _atr_now(candles, p.atr_period, atr_value)
    if a is None or len(candles) < 2:
        return None
    i = len(candles) - 1
    prev, cur = candles[i - 1], candles[i]
    g = cur.open - prev.close
    if abs(g) >= p.fvg_min_atr_frac * a and (cur.ts - prev.end_ts) > timedelta(0):
        return StructureEvent("GAP", "bullish" if g > 0 else "bearish", i, cur.ts, prev.close, "Observed liquidity pattern", f"gap {g:+.2f} over {(cur.ts - prev.end_ts)}")
    return None


def nearest_level(price: float, levels: Sequence[Level], kind: str | None = None) -> Level | None:
    cands = [l for l in levels if kind is None or l.kind == kind]
    if not cands:
        return None
    return min(cands, key=lambda l: abs(l.price - price))


@dataclass
class StructureSnapshot:
    timeframe: Timeframe
    trend: Trend
    swings: list[Swing]
    levels: list[Level]
    events: list[StructureEvent]
    range_state: RangeState | None
    volatility: str
    atr: float | None
    last_close: float

    def to_dict(self) -> dict:
        return {
            "timeframe": self.timeframe.value,
            "trend": self.trend.value,
            "atr": self.atr,
            "volatility": self.volatility,
            "last_close": self.last_close,
            "range": None if self.range_state is None else {"is_range": self.range_state.is_range, "high": self.range_state.high, "low": self.range_state.low, "width_atr": round(self.range_state.width_atr, 2)},
            "levels": [{"name": l.name, "price": l.price, "kind": l.kind, "source": l.source} for l in self.levels],
            "swings": [{"kind": s.kind.value, "ts": s.ts.isoformat(), "price": s.price} for s in self.swings[-8:]],
            "events": [{"kind": e.kind, "direction": e.direction, "ts": e.ts.isoformat(), "level": e.level, "label": e.label, "detail": e.detail} for e in self.events],
        }


def analyse_structure(candles: Sequence[Candle], as_of: datetime, p: StructureParams = StructureParams(), daily_candles: Sequence[Candle] | None = None) -> StructureSnapshot:
    """Full structure snapshot for one timeframe using only candles closed before as_of."""
    cs = [c for c in candles if c.complete and c.end_ts <= ensure_utc(as_of)]
    if not cs:
        raise ValueError("no closed candles")
    tf = cs[0].timeframe
    swings = find_swings(cs, p)
    trend = classify_trend(swings)
    a = _atr_now(cs, p.atr_period)
    levels: list[Level] = []
    levels += previous_period_levels(daily_candles or cs, as_of)
    if tf.seconds <= 3600:
        levels += session_levels(cs, as_of)
    levels += swing_levels(swings)
    events: list[StructureEvent] = []
    if a:
        events += equal_levels(swings, a, p)
        for det in (detect_displacement, detect_fvg, detect_gap):
            e = det(cs, p, a)
            if e:
                events.append(e)
        rej = detect_rejection(cs, p)
        if rej:
            events.append(rej)
        bos = break_of_structure(cs, swings, p, a)
        if bos:
            events.append(bos)
        for lvl in levels:
            for det in (detect_breakout, detect_failed_breakout, detect_sweep):
                e = det(cs, lvl, p, a)  # type: ignore[operator]
                if e:
                    events.append(e)
    return StructureSnapshot(tf, trend, swings, levels, events, consolidation_range(cs, p, a), volatility_state(cs, p), a, cs[-1].close)
