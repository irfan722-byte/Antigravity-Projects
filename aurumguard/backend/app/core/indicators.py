"""Deterministic technical indicators over closed candles.

All functions accept plain Python sequences of floats (or Candle lists via the
helpers at the bottom) and return numpy arrays aligned to the input, with NaN
during the warm-up period. No function reads beyond index i when producing
value i, which keeps them free of look-ahead by construction.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from .candles import Candle

NaN = float("nan")


def _arr(x: Sequence[float]) -> np.ndarray:
    return np.asarray(x, dtype=float)


def sma(values: Sequence[float], period: int) -> np.ndarray:
    v = _arr(values)
    out = np.full(v.shape, NaN)
    if period <= 0 or len(v) < period:
        return out
    c = np.cumsum(np.insert(v, 0, 0.0))
    out[period - 1 :] = (c[period:] - c[:-period]) / period
    return out


def ema(values: Sequence[float], period: int) -> np.ndarray:
    v = _arr(values)
    out = np.full(v.shape, NaN)
    if period <= 0 or len(v) < period:
        return out
    k = 2.0 / (period + 1)
    out[period - 1] = v[:period].mean()
    for i in range(period, len(v)):
        out[i] = v[i] * k + out[i - 1] * (1 - k)
    return out


def _wilder(values: np.ndarray, period: int) -> np.ndarray:
    out = np.full(values.shape, NaN)
    n = len(values)
    if n < period:
        return out
    prev = float(values[:period].mean())
    out[period - 1] = prev
    vals = values.tolist()
    k = (period - 1) / period
    inv = 1.0 / period
    for i in range(period, n):
        prev = prev * k + vals[i] * inv
        out[i] = prev
    return out


def true_range(high: Sequence[float], low: Sequence[float], close: Sequence[float]) -> np.ndarray:
    h, l, c = _arr(high), _arr(low), _arr(close)
    tr = h - l
    if len(h) > 1:
        pc = c[:-1]
        tr[1:] = np.maximum(tr[1:], np.maximum(np.abs(h[1:] - pc), np.abs(l[1:] - pc)))
    return tr


def atr(high: Sequence[float], low: Sequence[float], close: Sequence[float], period: int = 14) -> np.ndarray:
    return _wilder(true_range(high, low, close), period)


def rsi(values: Sequence[float], period: int = 14) -> np.ndarray:
    v = _arr(values)
    out = np.full(v.shape, NaN)
    if len(v) <= period:
        return out
    delta = np.diff(v)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    ag = _wilder(gains, period)
    al = _wilder(losses, period)
    for i in range(period - 1, len(delta)):
        if math.isnan(ag[i]):
            continue
        if al[i] == 0:
            out[i + 1] = 100.0
        else:
            rs = ag[i] / al[i]
            out[i + 1] = 100.0 - 100.0 / (1.0 + rs)
    return out


def adx(high: Sequence[float], low: Sequence[float], close: Sequence[float], period: int = 14) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (adx, +DI, -DI)."""
    h, l, c = _arr(high), _arr(low), _arr(close)
    n = len(h)
    adx_out = np.full(n, NaN)
    pdi_out = np.full(n, NaN)
    mdi_out = np.full(n, NaN)
    if n < 2 * period + 1:
        return adx_out, pdi_out, mdi_out
    tr = true_range(h, l, c)
    pdm = np.zeros(n)
    mdm = np.zeros(n)
    for i in range(1, n):
        up = h[i] - h[i - 1]
        dn = l[i - 1] - l[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        mdm[i] = dn if (dn > up and dn > 0) else 0.0
    atr_w = _wilder(tr[1:], period)
    pdm_w = _wilder(pdm[1:], period)
    mdm_w = _wilder(mdm[1:], period)
    dx = np.full(n - 1, NaN)
    for i in range(period - 1, n - 1):
        if atr_w[i] and not math.isnan(atr_w[i]):
            pdi = 100 * pdm_w[i] / atr_w[i]
            mdi = 100 * mdm_w[i] / atr_w[i]
            pdi_out[i + 1] = pdi
            mdi_out[i + 1] = mdi
            s = pdi + mdi
            dx[i] = 100 * abs(pdi - mdi) / s if s else 0.0
    valid = dx[period - 1 :]
    adx_w = _wilder(valid, period)
    adx_out[2 * period - 1 + 1 :] = adx_w[period - 1 :][: n - 2 * period]
    return adx_out, pdi_out, mdi_out


def roc(values: Sequence[float], period: int) -> np.ndarray:
    v = _arr(values)
    out = np.full(v.shape, NaN)
    if len(v) <= period:
        return out
    out[period:] = (v[period:] - v[:-period]) / v[:-period] * 100.0
    return out


def bollinger(values: Sequence[float], period: int = 20, k: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return (middle, upper, lower, bandwidth)."""
    v = _arr(values)
    mid = sma(v, period)
    std = np.full(v.shape, NaN)
    for i in range(period - 1, len(v)):
        std[i] = v[i - period + 1 : i + 1].std(ddof=0)
    upper = mid + k * std
    lower = mid - k * std
    with np.errstate(invalid="ignore", divide="ignore"):
        bw = (upper - lower) / mid
    return mid, upper, lower, bw


def donchian(high: Sequence[float], low: Sequence[float], period: int = 20) -> tuple[np.ndarray, np.ndarray]:
    """Upper/lower channel using the *previous* ``period`` bars (excludes current bar)."""
    h, l = _arr(high), _arr(low)
    up = np.full(h.shape, NaN)
    dn = np.full(h.shape, NaN)
    for i in range(period, len(h)):
        up[i] = h[i - period : i].max()
        dn[i] = l[i - period : i].min()
    return up, dn


def realised_vol(close: Sequence[float], period: int = 20, annualise_periods: int | None = None) -> np.ndarray:
    """Standard deviation of log returns over ``period`` bars (optionally annualised)."""
    c = _arr(close)
    out = np.full(c.shape, NaN)
    if len(c) <= period:
        return out
    lr = np.diff(np.log(c))
    # rolling sample std via cumulative sums (window = period, ending at lr index i-1 for out[i])
    cs = np.cumsum(np.insert(lr, 0, 0.0))
    cs2 = np.cumsum(np.insert(lr * lr, 0, 0.0))
    idx = np.arange(period, len(c))
    s1 = cs[idx] - cs[idx - period]
    s2 = cs2[idx] - cs2[idx - period]
    var = np.maximum((s2 - s1 * s1 / period) / (period - 1), 0.0)
    out[period:] = np.sqrt(var)
    if annualise_periods:
        out *= math.sqrt(annualise_periods)
    return out


def vwap(high: Sequence[float], low: Sequence[float], close: Sequence[float], volume: Sequence[float | None], anchor_indices: Sequence[int]) -> np.ndarray:
    """Anchored VWAP. Resets at each index in ``anchor_indices``. Requires real or clearly labelled proxy volume.

    Returns NaN wherever volume is missing since the last anchor.
    """
    h, l, c = _arr(high), _arr(low), _arr(close)
    n = len(c)
    out = np.full(n, NaN)
    anchors = set(anchor_indices)
    pv = 0.0
    vv = 0.0
    broken = False
    for i in range(n):
        if i in anchors or i == 0:
            pv, vv, broken = 0.0, 0.0, False
        vol = volume[i]
        if vol is None:
            broken = True
        if broken:
            continue
        tp = (h[i] + l[i] + c[i]) / 3.0
        pv += tp * float(vol)  # type: ignore[arg-type]
        vv += float(vol)  # type: ignore[arg-type]
        out[i] = pv / vv if vv else NaN
    return out


# ---- candle helpers -------------------------------------------------------

def closes(candles: Sequence[Candle]) -> list[float]:
    return [c.close for c in candles]


def highs(candles: Sequence[Candle]) -> list[float]:
    return [c.high for c in candles]


def lows(candles: Sequence[Candle]) -> list[float]:
    return [c.low for c in candles]


def last_valid(arr: np.ndarray) -> float | None:
    for x in arr[::-1]:
        if not math.isnan(x):
            return float(x)
    return None
