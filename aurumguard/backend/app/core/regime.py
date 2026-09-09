"""Market-regime engine.

Deterministic classification from measurable inputs. Every measurement that
influenced the result is reported as supporting or conflicting so the
Evidence Inspector can show the working. If the inputs are insufficient the
result is UNKNOWN and strategies that require a confirmed regime are disabled
by the decision engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Sequence

import numpy as np

from .candles import Candle
from .indicators import adx, closes, highs, last_valid, lows, realised_vol
from .structure import StructureSnapshot, Trend


class Regime(str, Enum):
    STRONG_TREND = "STRONG_TREND"
    WEAK_TREND = "WEAK_TREND"
    RANGE = "RANGE"
    VOLATILITY_COMPRESSION = "VOLATILITY_COMPRESSION"
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    NEWS_DOMINATED = "NEWS_DOMINATED"
    DOLLAR_DRIVEN = "DOLLAR_DRIVEN"
    YIELD_DRIVEN = "YIELD_DRIVEN"
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    THIN_LIQUIDITY = "THIN_LIQUIDITY"
    TRANSITION = "TRANSITION"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RegimeParams:
    adx_period: int = 14
    adx_strong: float = 25.0
    adx_weak: float = 18.0
    vol_lookback: int = 100
    vol_high_pct: float = 80.0
    vol_low_pct: float = 20.0
    corr_window: int = 30
    corr_threshold: float = -0.5
    driver_move_threshold_pct: float = 0.75  # 5-bar move in DXY (%) to call dollar-driven
    yield_move_threshold_bp: float = 12.0  # 5-bar move in 10y (bp) to call yield-driven
    thin_spread_ratio: float = 2.0
    min_bars: int = 60


@dataclass(frozen=True)
class IntermarketInputs:
    """Aligned daily closes for cross-market series (same length, same dates), newest last."""

    gold: Sequence[float]
    dxy: Sequence[float] | None = None
    us10y: Sequence[float] | None = None  # percent, e.g. 4.25
    us2y: Sequence[float] | None = None
    real_yield_proxy: Sequence[float] | None = None
    risk_index: Sequence[float] | None = None  # e.g. broad equity index, public
    vol_index: Sequence[float] | None = None  # public volatility index if licensed
    as_of: datetime | None = None


@dataclass
class RegimeAssessment:
    primary: Regime
    tags: list[Regime]
    confidence: float
    supporting: list[str]
    conflicting: list[str]
    measurements: dict = field(default_factory=dict)
    trend_direction: str = "NONE"  # UP / DOWN / NONE
    as_of: datetime | None = None
    version: str = "regime-v1"

    def to_dict(self) -> dict:
        return {
            "primary": self.primary.value,
            "tags": [t.value for t in self.tags],
            "confidence": round(self.confidence, 3),
            "trend_direction": self.trend_direction,
            "supporting": self.supporting,
            "conflicting": self.conflicting,
            "measurements": self.measurements,
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "version": self.version,
        }

    def has(self, r: Regime) -> bool:
        return r == self.primary or r in self.tags


def _corr(a: Sequence[float], b: Sequence[float], window: int) -> float | None:
    if a is None or b is None or len(a) < window + 1 or len(b) < window + 1:
        return None
    ra = np.diff(np.log(np.asarray(a[-window - 1 :], dtype=float)))
    rb = np.diff(np.asarray(b[-window - 1 :], dtype=float))
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def _pct_rank(values: np.ndarray, x: float) -> float | None:
    v = values[~np.isnan(values)]
    if len(v) < 10:
        return None
    return float((v < x).mean() * 100.0)


def classify_regime(
    anchor_candles: Sequence[Candle],
    structure: StructureSnapshot | None,
    higher_structure: StructureSnapshot | None,
    intermarket: IntermarketInputs | None,
    news_phase: str,
    session_label: str,
    current_spread: float | None,
    median_spread: float | None,
    as_of: datetime,
    p: RegimeParams = RegimeParams(),
) -> RegimeAssessment:
    """Classify using the anchor timeframe (normally H4) plus higher-timeframe (D1) structure."""
    supporting: list[str] = []
    conflicting: list[str] = []
    tags: list[Regime] = []
    meas: dict = {}
    cs = [c for c in anchor_candles if c.complete]
    if len(cs) < p.min_bars:
        return RegimeAssessment(Regime.UNKNOWN, [], 0.0, [], [f"only {len(cs)} anchor bars (<{p.min_bars})"], {"bars": len(cs)}, as_of=as_of)

    h, l, c = highs(cs), lows(cs), closes(cs)
    adx_arr, pdi, mdi = adx(h, l, c, p.adx_period)
    adx_now = last_valid(adx_arr)
    pdi_now, mdi_now = last_valid(pdi), last_valid(mdi)
    meas["adx"] = adx_now
    meas["plus_di"] = pdi_now
    meas["minus_di"] = mdi_now
    trend_dir = "NONE"
    struct_trend = structure.trend if structure else Trend.UNKNOWN
    meas["structure_trend"] = struct_trend.value
    if pdi_now is not None and mdi_now is not None:
        di_dir = "UP" if pdi_now > mdi_now else "DOWN"
    else:
        di_dir = "NONE"

    primary: Regime | None = None
    if adx_now is not None:
        if adx_now >= p.adx_strong and di_dir != "NONE":
            if struct_trend.value == di_dir:
                primary = Regime.STRONG_TREND
                trend_dir = di_dir
                supporting.append(f"ADX {adx_now:.1f} >= {p.adx_strong} with DI direction {di_dir} confirmed by swing structure")
            elif struct_trend in (Trend.UNKNOWN, Trend.SIDEWAYS):
                primary = Regime.WEAK_TREND
                trend_dir = di_dir
                supporting.append(f"ADX {adx_now:.1f} strong but swing structure {struct_trend.value} does not confirm")
                conflicting.append("swing structure not confirming DI direction")
            else:
                primary = Regime.TRANSITION
                conflicting.append(f"DI direction {di_dir} opposes swing structure {struct_trend.value}")
        elif adx_now >= p.adx_weak and di_dir != "NONE":
            primary = Regime.WEAK_TREND
            trend_dir = di_dir if struct_trend.value in (di_dir, "UNKNOWN", "SIDEWAYS") else "NONE"
            supporting.append(f"ADX {adx_now:.1f} between {p.adx_weak} and {p.adx_strong}")
            if struct_trend.value not in (di_dir, "UNKNOWN", "SIDEWAYS"):
                conflicting.append(f"structure {struct_trend.value} opposes DI {di_dir}")
        else:
            if structure and structure.range_state and structure.range_state.is_range:
                primary = Regime.RANGE
                supporting.append(f"ADX {adx_now:.1f} < {p.adx_weak} and {structure.range_state.width_atr:.1f} ATR range width")
            else:
                primary = Regime.RANGE
                supporting.append(f"ADX {adx_now:.1f} < {p.adx_weak}")
                if structure and structure.range_state:
                    conflicting.append(f"lookback width {structure.range_state.width_atr:.1f} ATR is wide for a range")
    else:
        conflicting.append("ADX unavailable")

    # higher timeframe agreement
    if higher_structure is not None and structure is not None:
        meas["higher_tf_trend"] = higher_structure.trend.value
        if higher_structure.trend in (Trend.UP, Trend.DOWN) and structure.trend in (Trend.UP, Trend.DOWN):
            if higher_structure.trend != structure.trend:
                conflicting.append(f"D1 trend {higher_structure.trend.value} vs anchor trend {structure.trend.value}")
                tags.append(Regime.TRANSITION)
            else:
                supporting.append(f"D1 and anchor trends agree ({structure.trend.value})")

    # volatility
    rv = realised_vol(c, 20)
    rv_now = last_valid(rv)
    pct = _pct_rank(rv[-p.vol_lookback :], rv_now) if rv_now is not None else None
    meas["realised_vol_20"] = rv_now
    meas["realised_vol_pct_rank"] = pct
    if pct is not None:
        if pct >= p.vol_high_pct:
            tags.append(Regime.HIGH_VOLATILITY)
            supporting.append(f"realised vol at {pct:.0f}th percentile")
        elif pct <= p.vol_low_pct:
            tags.append(Regime.LOW_VOLATILITY)
            supporting.append(f"realised vol at {pct:.0f}th percentile")
    if structure is not None:
        meas["atr_state"] = structure.volatility
        if structure.volatility == "EXPANSION":
            tags.append(Regime.VOLATILITY_EXPANSION)
        elif structure.volatility == "CONTRACTION":
            tags.append(Regime.VOLATILITY_COMPRESSION)

    # intermarket
    if intermarket is not None:
        corr_dxy = _corr(intermarket.gold, intermarket.dxy, p.corr_window) if intermarket.dxy else None
        corr_10y = _corr(intermarket.gold, intermarket.us10y, p.corr_window) if intermarket.us10y else None
        meas["corr_gold_dxy"] = corr_dxy
        meas["corr_gold_us10y"] = corr_10y
        if intermarket.dxy and len(intermarket.dxy) >= 6:
            mv = (intermarket.dxy[-1] / intermarket.dxy[-6] - 1) * 100
            meas["dxy_5bar_move_pct"] = mv
            if corr_dxy is not None and corr_dxy <= p.corr_threshold and abs(mv) >= p.driver_move_threshold_pct:
                tags.append(Regime.DOLLAR_DRIVEN)
                supporting.append(f"gold/DXY correlation {corr_dxy:.2f}, DXY moved {mv:+.2f}% over 5 bars")
        if intermarket.us10y and len(intermarket.us10y) >= 6:
            mvbp = (intermarket.us10y[-1] - intermarket.us10y[-6]) * 100
            meas["us10y_5bar_move_bp"] = mvbp
            if corr_10y is not None and corr_10y <= p.corr_threshold and abs(mvbp) >= p.yield_move_threshold_bp:
                tags.append(Regime.YIELD_DRIVEN)
                supporting.append(f"gold/10y correlation {corr_10y:.2f}, 10y moved {mvbp:+.0f}bp over 5 bars")
        if intermarket.risk_index and len(intermarket.risk_index) >= 6:
            rmv = (intermarket.risk_index[-1] / intermarket.risk_index[-6] - 1) * 100
            meas["risk_index_5bar_move_pct"] = rmv
            vmv = None
            if intermarket.vol_index and len(intermarket.vol_index) >= 6:
                vmv = (intermarket.vol_index[-1] / intermarket.vol_index[-6] - 1) * 100
                meas["vol_index_5bar_move_pct"] = vmv
            if rmv >= 1.5 and (vmv is None or vmv <= 0):
                tags.append(Regime.RISK_ON)
            elif rmv <= -1.5 and (vmv is None or vmv >= 0):
                tags.append(Regime.RISK_OFF)

    # news / liquidity
    meas["news_phase"] = news_phase
    meas["session"] = session_label
    if news_phase in ("PRE_EVENT_WINDOW", "RELEASE_LOCKOUT", "POST_RELEASE_COOLDOWN"):
        tags.append(Regime.NEWS_DOMINATED)
        supporting.append(f"news phase {news_phase}")
    if session_label == "OFF_HOURS":
        tags.append(Regime.THIN_LIQUIDITY)
    if current_spread is not None and median_spread:
        meas["spread_ratio"] = current_spread / median_spread
        if current_spread / median_spread >= p.thin_spread_ratio:
            if Regime.THIN_LIQUIDITY not in tags:
                tags.append(Regime.THIN_LIQUIDITY)
            supporting.append(f"spread {current_spread:.2f} is {current_spread / median_spread:.1f}x median")

    if primary is None:
        primary = Regime.UNKNOWN
    if len(conflicting) > len(supporting) and primary != Regime.UNKNOWN:
        conflicting.append("conflicting measurements outnumber supporting: downgraded to MIXED")
        primary = Regime.MIXED
    total = len(supporting) + len(conflicting)
    conf = (len(supporting) / total) if total else 0.0
    if primary in (Regime.UNKNOWN, Regime.MIXED):
        conf = min(conf, 0.4)
    return RegimeAssessment(primary, tags, conf, supporting, conflicting, meas, trend_dir, as_of)
