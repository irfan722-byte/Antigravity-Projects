"""Data-integrity engine.

Validates quotes, candle series, cross-provider agreement and event timestamps.
It never repairs or fills data: it reports, and the decision engine turns
INVALID or stale results into DATA UNAVAILABLE.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Sequence

from .candles import Candle, Quote, Timeframe
from .timeutil import MarketState, ensure_utc, market_state


class Severity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class DataStatus(str, Enum):
    VALID = "VALID"
    DEGRADED = "DEGRADED"
    INVALID = "INVALID"


@dataclass(frozen=True)
class Issue:
    code: str
    severity: Severity
    message: str
    ts: datetime | None = None


@dataclass
class IntegrityReport:
    subject: str
    status: DataStatus = DataStatus.VALID
    issues: list[Issue] = field(default_factory=list)
    checked_at: datetime | None = None
    freshness_seconds: float | None = None

    def add(self, code: str, severity: Severity, message: str, ts: datetime | None = None) -> None:
        self.issues.append(Issue(code, severity, message, ts))
        if severity == Severity.ERROR:
            self.status = DataStatus.INVALID
        elif severity == Severity.WARN and self.status == DataStatus.VALID:
            self.status = DataStatus.DEGRADED

    @property
    def ok(self) -> bool:
        return self.status != DataStatus.INVALID

    def codes(self) -> list[str]:
        return [i.code for i in self.issues]

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "status": self.status.value,
            "freshness_seconds": self.freshness_seconds,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
            "issues": [
                {"code": i.code, "severity": i.severity.value, "message": i.message, "ts": i.ts.isoformat() if i.ts else None}
                for i in self.issues
            ],
        }


@dataclass(frozen=True)
class IntegrityConfig:
    quote_max_age_seconds: float = 20.0
    candle_stale_multiplier: float = 2.0  # last complete candle older than tf*mult => stale
    max_spread_abs: float = 3.0  # USD; sanity cap, user risk limit is separate
    outlier_return_sigma: float = 8.0
    outlier_window: int = 50
    cross_provider_max_bps: float = 15.0
    future_tolerance_seconds: float = 5.0
    max_gap_candles_open_market: int = 1


# ---------------------------------------------------------------- quotes --

def validate_quote(q: Quote, now: datetime, cfg: IntegrityConfig = IntegrityConfig()) -> IntegrityReport:
    r = IntegrityReport(subject=f"quote:{q.instrument}:{q.provider}", checked_at=ensure_utc(now))
    now = ensure_utc(now)
    try:
        ts = ensure_utc(q.ts)
        ing = ensure_utc(q.ingested_at)
    except ValueError as exc:
        r.add("QUOTE_NAIVE_TS", Severity.ERROR, str(exc))
        return r
    if ts > now + timedelta(seconds=cfg.future_tolerance_seconds):
        r.add("QUOTE_FUTURE_TS", Severity.ERROR, f"quote timestamp {ts.isoformat()} is in the future", ts)
    if ing < ts - timedelta(seconds=cfg.future_tolerance_seconds):
        r.add("QUOTE_INGEST_BEFORE_SOURCE", Severity.ERROR, "ingested before source timestamp", ts)
    if not (math.isfinite(q.bid) and math.isfinite(q.ask)) or q.bid <= 0 or q.ask <= 0:
        r.add("QUOTE_INVALID_PRICE", Severity.ERROR, f"bid={q.bid} ask={q.ask}", ts)
        return r
    spread = q.ask - q.bid
    if spread < 0:
        r.add("QUOTE_NEGATIVE_SPREAD", Severity.ERROR, f"ask {q.ask} < bid {q.bid}", ts)
    elif spread == 0:
        r.add("QUOTE_ZERO_SPREAD", Severity.WARN, "zero spread is implausible for XAU/USD; provider may send mid only", ts)
    elif spread > cfg.max_spread_abs:
        r.add("QUOTE_EXTREME_SPREAD", Severity.ERROR, f"spread {spread:.2f} exceeds sanity cap {cfg.max_spread_abs}", ts)
    age = (now - ts).total_seconds()
    r.freshness_seconds = age
    if age > cfg.quote_max_age_seconds:
        r.add("QUOTE_STALE", Severity.ERROR, f"quote is {age:.0f}s old (limit {cfg.quote_max_age_seconds:.0f}s)", ts)
    return r


# --------------------------------------------------------------- candles --

def validate_candles(
    candles: Sequence[Candle],
    timeframe: Timeframe,
    now: datetime,
    cfg: IntegrityConfig = IntegrityConfig(),
    holiday_dates: set | None = None,
) -> IntegrityReport:
    now = ensure_utc(now)
    r = IntegrityReport(subject=f"candles:{timeframe.value}", checked_at=now)
    if not candles:
        r.add("CANDLES_EMPTY", Severity.ERROR, "no candles supplied")
        return r
    prev: Candle | None = None
    seen: set[datetime] = set()
    closes: list[float] = []
    for c in candles:
        try:
            ts = ensure_utc(c.ts)
        except ValueError as exc:
            r.add("CANDLE_NAIVE_TS", Severity.ERROR, str(exc))
            return r
        if c.timeframe != timeframe:
            r.add("CANDLE_TF_MISMATCH", Severity.ERROR, f"candle at {ts.isoformat()} has tf {c.timeframe.value}", ts)
        if ts in seen:
            r.add("CANDLE_DUPLICATE", Severity.ERROR, f"duplicate candle at {ts.isoformat()}", ts)
        seen.add(ts)
        if prev is not None and ts < prev.ts:
            r.add("CANDLE_OUT_OF_ORDER", Severity.ERROR, f"{ts.isoformat()} before {prev.ts.isoformat()}", ts)
        if timeframe != Timeframe.W1 and int(ts.timestamp()) % timeframe.seconds != 0:
            r.add("CANDLE_MISALIGNED", Severity.WARN, f"candle open {ts.isoformat()} is not aligned to {timeframe.value}", ts)
        if any(not math.isfinite(x) or x <= 0 for x in (c.open, c.high, c.low, c.close)):
            r.add("CANDLE_INVALID_PRICE", Severity.ERROR, f"non-positive/non-finite price at {ts.isoformat()}", ts)
            prev = c
            continue
        if c.high < c.low or c.open > c.high or c.open < c.low or c.close > c.high or c.close < c.low:
            r.add("CANDLE_OHLC_INCONSISTENT", Severity.ERROR, f"OHLC inconsistent at {ts.isoformat()}", ts)
        if c.spread_close is not None and c.spread_close < 0:
            r.add("CANDLE_NEGATIVE_SPREAD", Severity.ERROR, f"negative spread at {ts.isoformat()}", ts)
        if c.end_ts > now + timedelta(seconds=cfg.future_tolerance_seconds) and c.complete:
            r.add("CANDLE_COMPLETE_IN_FUTURE", Severity.ERROR, f"candle ending {c.end_ts.isoformat()} marked complete before it ended", ts)
        if prev is not None and c.complete and prev.complete:
            gap = int((ts - prev.ts).total_seconds() // timeframe.seconds) - 1
            if gap > cfg.max_gap_candles_open_market and timeframe.seconds < 86400:
                # only a problem if the market was open during the gap
                probe = prev.end_ts + timedelta(seconds=timeframe.seconds // 2)
                open_missing = 0
                while probe < ts:
                    if market_state(probe, holiday_dates) == MarketState.OPEN:
                        open_missing += 1
                    probe += timeframe.delta
                if open_missing > cfg.max_gap_candles_open_market:
                    r.add("CANDLE_GAP", Severity.WARN, f"{open_missing} candles missing during open market before {ts.isoformat()}", ts)
        if closes and c.complete:
            n = min(cfg.outlier_window, len(closes))
            window = closes[-n:]
            if n >= 10:
                rets = [math.log(window[i] / window[i - 1]) for i in range(1, n)]
                mu = sum(rets) / len(rets)
                sd = math.sqrt(sum((x - mu) ** 2 for x in rets) / max(1, len(rets) - 1))
                cur = math.log(c.close / closes[-1])
                if sd > 0 and abs(cur - mu) / sd > cfg.outlier_return_sigma:
                    r.add("CANDLE_OUTLIER", Severity.WARN, f"return {cur:.4%} at {ts.isoformat()} is {abs(cur - mu) / sd:.1f} sigma", ts)
        if c.complete:
            closes.append(c.close)
        prev = c
    complete = [c for c in candles if c.complete]
    if complete:
        last_end = complete[-1].end_ts
        age = (now - last_end).total_seconds()
        r.freshness_seconds = age
        limit = timeframe.seconds * cfg.candle_stale_multiplier
        if age > limit and market_state(now, holiday_dates) == MarketState.OPEN:
            r.add("CANDLES_STALE", Severity.ERROR, f"last complete candle ended {age:.0f}s ago (limit {limit:.0f}s while market open)")
    else:
        r.add("CANDLES_NO_COMPLETE", Severity.ERROR, "no complete candles")
    return r


# ------------------------------------------------------- cross provider --

def compare_quotes(primary: Quote, secondary: Quote, cfg: IntegrityConfig = IntegrityConfig()) -> IntegrityReport:
    r = IntegrityReport(subject=f"xprov:{primary.provider}~{secondary.provider}", checked_at=ensure_utc(max(primary.ingested_at, secondary.ingested_at)))
    if primary.mid <= 0 or secondary.mid <= 0:
        r.add("XPROV_INVALID", Severity.ERROR, "invalid mid price")
        return r
    diff_bps = abs(primary.mid - secondary.mid) / primary.mid * 1e4
    if diff_bps > cfg.cross_provider_max_bps:
        r.add("XPROV_DISAGREE", Severity.ERROR, f"providers differ by {diff_bps:.1f} bps (limit {cfg.cross_provider_max_bps})")
    elif diff_bps > cfg.cross_provider_max_bps / 2:
        r.add("XPROV_DRIFT", Severity.WARN, f"providers differ by {diff_bps:.1f} bps")
    return r


# --------------------------------------------------------- event checks --

def validate_event_timestamp(scheduled: datetime, published: datetime | None, ingested: datetime, now: datetime) -> IntegrityReport:
    """Verify an economic event's timestamps are coherent and timezone aware."""
    r = IntegrityReport(subject="event_ts", checked_at=ensure_utc(now))
    try:
        s = ensure_utc(scheduled)
        i = ensure_utc(ingested)
        p = ensure_utc(published) if published else None
    except ValueError as exc:
        r.add("EVENT_NAIVE_TS", Severity.ERROR, str(exc))
        return r
    if p is not None:
        if p < s - timedelta(minutes=1):
            r.add("EVENT_PUBLISHED_BEFORE_SCHEDULE", Severity.ERROR, "actual published before scheduled release; leakage or timezone error")
        if i < p - timedelta(seconds=5):
            r.add("EVENT_INGESTED_BEFORE_PUBLISH", Severity.ERROR, "ingested before publication timestamp")
        if p - s > timedelta(minutes=30):
            r.add("EVENT_DELAYED_RELEASE", Severity.WARN, f"release delayed {(p - s).total_seconds() / 60:.0f} min")
    return r


def merge_reports(reports: Sequence[IntegrityReport]) -> DataStatus:
    if any(r.status == DataStatus.INVALID for r in reports):
        return DataStatus.INVALID
    if any(r.status == DataStatus.DEGRADED for r in reports):
        return DataStatus.DEGRADED
    return DataStatus.VALID
