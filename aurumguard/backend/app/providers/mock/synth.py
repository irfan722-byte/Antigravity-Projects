"""Deterministic synthetic XAU/USD generator for DEMO mode, tests and backtest plumbing checks.

This is NOT market data. Every record is stamped provider="mock" and the UI
shows a DEMO DATA banner whenever this provider is active.

Design:
- The path is a pure function of (params, minute index since ORIGIN): every
  random stream has its own seed so extending the horizon never changes
  earlier values (prefix stability).
- Generation and resampling are vectorised over numpy arrays; Candle objects
  are only materialised for the slice a caller asks for.
- Session-dependent volatility, off-hours/event spread widening, small
  regime-switching drift.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Sequence

import numpy as np

from ...core.candles import Candle, Quote, Timeframe
from ...core.timeutil import NY, session_label

UTC = UTC
PROVIDER = "mock"
ORIGIN = datetime(2024, 1, 1, tzinfo=UTC)  # a Monday


@dataclass(frozen=True)
class SynthParams:
    seed: int = 20260101
    start_price: float = 2400.0
    base_minute_vol: float = 0.00022  # ~0.35% daily
    regime_switch_prob: float = 0.002  # per minute (~every 8 open hours)
    regime_drift: float = 0.000012  # per minute while in a trending regime
    base_spread: float = 0.25
    offhours_spread: float = 0.55
    event_spread: float = 1.20


@dataclass
class SynthPath:
    """Open-market minutes only. ``minute`` = minutes since ORIGIN."""

    minute: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    spread: np.ndarray
    end_minute: int


def _rng(seed: int, salt: str) -> np.random.Generator:
    h = hashlib.sha256(f"{seed}:{salt}".encode()).digest()
    return np.random.default_rng(int.from_bytes(h[:8], "little"))


def _session_vol_mult_label(lab: str) -> float:
    if lab == "LONDON_NY_OVERLAP":
        return 1.6
    if "NEW_YORK" in lab or "LONDON" in lab:
        return 1.25
    if lab == "ASIA":
        return 0.7
    return 0.45


def _spread_for_label(lab: str, p: SynthParams) -> float:
    if lab == "OFF_HOURS":
        return p.offhours_spread
    if lab == "ASIA":
        return p.base_spread * 1.4
    return p.base_spread


def spread_at(ts: datetime, p: SynthParams = SynthParams(), event_windows: Sequence[tuple[datetime, datetime]] = ()) -> float:
    for a, b in event_windows:
        if a <= ts < b:
            return p.event_spread
    return _spread_for_label(session_label(ts), p)


_HOUR_CACHE: dict[int, tuple[np.ndarray, np.ndarray, list[str]]] = {}


def _hourly_context(n_hours: int) -> tuple[np.ndarray, np.ndarray, list[str]]:
    cached = _HOUR_CACHE.get(0)
    if cached and len(cached[0]) >= n_hours:
        return cached[0][:n_hours], cached[1][:n_hours], cached[2][:n_hours]
    ny_off = np.empty(n_hours, dtype=np.int64)
    vol_mult = np.empty(n_hours, dtype=float)
    labels: list[str] = []
    t = ORIGIN
    for i in range(n_hours):
        ny_off[i] = int(t.astimezone(NY).utcoffset().total_seconds() // 60)
        lab = session_label(t + timedelta(minutes=30))
        vol_mult[i] = _session_vol_mult_label(lab)
        labels.append(lab)
        t += timedelta(hours=1)
    _HOUR_CACHE[0] = (ny_off, vol_mult, labels)
    return ny_off, vol_mult, labels


_PATH_CACHE: dict[tuple, SynthPath] = {}


def generate_path(end: datetime, p: SynthParams = SynthParams(), event_windows: Sequence[tuple[datetime, datetime]] = ()) -> SynthPath:
    """Path from ORIGIN to ``end`` (exclusive), open-market minutes only. Cached and prefix-stable."""
    end = end.astimezone(UTC)
    n = int((end - ORIGIN).total_seconds() // 60)
    n = max(n, 0)
    key = (p, tuple(event_windows))
    cached = _PATH_CACHE.get(key)
    if cached and cached.end_minute >= n:
        if cached.end_minute == n:
            return cached
        k = int(np.searchsorted(cached.minute, n))
        return SynthPath(cached.minute[:k], cached.open[:k], cached.high[:k], cached.low[:k], cached.close[:k], cached.volume[:k], cached.spread[:k], n)
    n_hours = n // 60 + 1
    ny_off, vol_mult_h, labels_h = _hourly_context(n_hours)
    idx = np.arange(n)
    hour_idx = idx // 60
    local_min = idx + ny_off[hour_idx]
    dow = (local_min // 1440) % 7  # ORIGIN is Monday -> 0
    tod = local_min % 1440
    open_mask = ~((dow == 5) | ((dow == 6) & (tod < 18 * 60)) | ((dow == 4) & (tod >= 17 * 60)) | ((dow <= 3) & (tod >= 17 * 60) & (tod < 18 * 60)))

    switches = _rng(p.seed, "switch").random(n) < p.regime_switch_prob
    regime_vals = _rng(p.seed, "regime").choice([-1, 0, 0, 1], size=n)
    last_switch = np.maximum.accumulate(np.where(switches, idx, 0))
    regime = np.where(last_switch > 0, regime_vals[last_switch], 0)
    drift = regime * p.regime_drift
    vol = p.base_minute_vol * vol_mult_h[hour_idx]
    in_event = np.zeros(n, dtype=bool)
    for a, b in event_windows:
        ia = int((a.astimezone(UTC) - ORIGIN).total_seconds() // 60)
        ib = int((b.astimezone(UTC) - ORIGIN).total_seconds() // 60)
        in_event[max(0, ia) : max(0, ib)] = True
    vol = np.where(in_event, vol * 3.0, vol)
    z = _rng(p.seed, "z").standard_normal(n)
    r = np.where(open_mask, drift + vol * z, 0.0)
    years = idx / 525600.0
    logp = math.log(p.start_price) + np.cumsum(r) + 0.10 * years + 0.04 * np.sin(years * 2 * math.pi * 1.7)
    close = np.exp(logp)
    open_ = np.exp(logp - r)
    wick = np.abs(_rng(p.seed, "wick").standard_normal(n)) * vol * close * 0.6
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick * _rng(p.seed, "low").random(n)
    volume = np.floor(50 + 400 * vol_mult_h[hour_idx] * (1 + np.abs(r) / np.maximum(vol, 1e-12)))
    spread_h = np.asarray([_spread_for_label(l, p) for l in labels_h])
    spread = np.where(in_event, p.event_spread, spread_h[hour_idx])
    m = open_mask
    path = SynthPath(idx[m], np.round(open_[m], 2), np.round(high[m], 2), np.round(low[m], 2), np.round(close[m], 2), volume[m], spread[m], n)
    _PATH_CACHE.clear()
    _PATH_CACHE[key] = path
    return path


def _week_bucket(minute: np.ndarray) -> np.ndarray:
    return minute // (7 * 1440)  # ORIGIN is a Monday, so week buckets align to Monday 00:00 UTC


def resample_path(path: SynthPath, tf: Timeframe) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return (bucket_start_minute, o, h, l, c, v, spread_close) arrays for ``tf``."""
    if tf == Timeframe.M1:
        return path.minute, path.open, path.high, path.low, path.close, path.volume, path.spread
    step = tf.seconds // 60
    bucket = _week_bucket(path.minute) * (7 * 1440) if tf == Timeframe.W1 else (path.minute // step) * step
    starts, first_idx = np.unique(bucket, return_index=True)
    o = path.open[first_idx]
    h = np.maximum.reduceat(path.high, first_idx)
    l = np.minimum.reduceat(path.low, first_idx)
    last_idx = np.append(first_idx[1:], len(path.minute)) - 1
    c = path.close[last_idx]
    v = np.add.reduceat(path.volume, first_idx)
    sp = path.spread[last_idx]
    return starts, o, h, l, c, v, sp


def candles_from_arrays(tf: Timeframe, arrays: tuple, start: datetime, end: datetime, as_of: datetime, path: SynthPath | None = None) -> list[Candle]:
    """Candles with bucket start in [start, end). A bucket that has not closed by ``as_of`` is
    rebuilt from the M1 path restricted to minutes before ``as_of`` so it never contains the future."""
    starts, o, h, l, c, v, sp = arrays
    s_min = int((start.astimezone(UTC) - ORIGIN).total_seconds() // 60)
    e_min = int((end.astimezone(UTC) - ORIGIN).total_seconds() // 60)
    lo = int(np.searchsorted(starts, s_min, side="left"))
    hi = int(np.searchsorted(starts, e_min, side="left"))
    out: list[Candle] = []
    as_of_min = int((as_of.astimezone(UTC) - ORIGIN).total_seconds() // 60)
    tf_min = tf.seconds // 60
    tfd = tf.delta
    st = starts[lo:hi].tolist()
    ol, hl, ll, cl, vl, spl = o[lo:hi].tolist(), h[lo:hi].tolist(), l[lo:hi].tolist(), c[lo:hi].tolist(), v[lo:hi].tolist(), sp[lo:hi].tolist()
    tfv = tf.value
    for j, m in enumerate(st):
        ts = ORIGIN + timedelta(minutes=m)
        complete = m + tf_min <= as_of_min
        if complete or path is None:
            out.append(Candle("XAUUSD", tf, ts, ol[j], hl[j], ll[j], cl[j], vl[j], "tick_proxy", spl[j], complete, PROVIDER, ts + tfd if complete else as_of, f"mock:{tfv}:{m}"))
            continue
        a = int(np.searchsorted(path.minute, m, side="left"))
        b = int(np.searchsorted(path.minute, as_of_min, side="left"))
        if b <= a:
            continue  # bucket has no minutes yet
        out.append(Candle("XAUUSD", tf, ts, float(path.open[a]), float(path.high[a:b].max()), float(path.low[a:b].min()), float(path.close[b - 1]), float(path.volume[a:b].sum()), "tick_proxy", float(path.spread[b - 1]), False, PROVIDER, as_of, f"mock:{tf.value}:{ts.isoformat()}:forming"))
    return out


def minute_path(start: datetime, end: datetime, p: SynthParams = SynthParams(), event_windows: Sequence[tuple[datetime, datetime]] = ()) -> list[Candle]:
    """Convenience: M1 candles for [start, end) as Candle objects (all complete)."""
    path = generate_path(end, p, event_windows)
    return candles_from_arrays(Timeframe.M1, resample_path(path, Timeframe.M1), start, end, end)


def quote_at(ts: datetime, last_close: float, p: SynthParams = SynthParams(), event_windows: Sequence[tuple[datetime, datetime]] = ()) -> Quote:
    sp = spread_at(ts, p, event_windows)
    return Quote("XAUUSD", round(last_close - sp / 2, 2), round(last_close + sp / 2, 2), ts, PROVIDER, ts, provenance_id=f"mock-quote:{ts.isoformat()}")


def daily_series(start: datetime, end: datetime, seed_salt: str, start_value: float, daily_vol: float, drift: float = 0.0, p: SynthParams = SynthParams()) -> list[tuple[datetime, float]]:
    """Generic seeded daily random walk for macro/intermarket demo series (DXY, yields...)."""
    rng = _rng(p.seed, seed_salt)
    out: list[tuple[datetime, float]] = []
    v = start_value
    d = start.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    while d < end:
        if d.weekday() < 5:
            v = v * math.exp(drift + daily_vol * rng.standard_normal())
            out.append((d, round(v, 4)))
        d += timedelta(days=1)
    return out
