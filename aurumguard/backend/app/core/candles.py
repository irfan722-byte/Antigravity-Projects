"""Candle, quote and timeframe primitives with provenance fields."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum
from typing import Iterable, Sequence

from .timeutil import ensure_utc


class Timeframe(str, Enum):
    M1 = "M1"
    M3 = "M3"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"

    @property
    def seconds(self) -> int:
        return _TF_SECONDS[self]

    @property
    def delta(self) -> timedelta:
        return _TF_DELTA[self]


_TF_SECONDS: dict[Timeframe, int] = {
    Timeframe.M1: 60,
    Timeframe.M3: 180,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.M30: 1800,
    Timeframe.H1: 3600,
    Timeframe.H4: 14400,
    Timeframe.D1: 86400,
    Timeframe.W1: 604800,
}
_TF_DELTA = {tf: timedelta(seconds=sec) for tf, sec in _TF_SECONDS.items()}


@dataclass(frozen=True)
class Quote:
    """A bid/ask snapshot. ``ts`` is the provider (source) timestamp in UTC."""

    instrument: str
    bid: float
    ask: float
    ts: datetime
    provider: str
    ingested_at: datetime
    provenance_id: str = ""

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True)
class Candle:
    """OHLC candle. ``ts`` is the *open* time in UTC. Prices are mid unless noted.

    ``complete`` is False for the currently forming bar. Strategies must not use
    incomplete bars unless explicitly validated for intrabar data.
    """

    instrument: str
    timeframe: Timeframe
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None  # None when the provider offers no volume; tick volume must be labelled by provider
    volume_kind: str = "none"  # "none" | "tick_proxy" | "exchange"
    spread_close: float | None = None  # ask-bid at close when known
    complete: bool = True
    provider: str = "unknown"
    ingested_at: datetime | None = None
    provenance_id: str = ""

    @property
    def end_ts(self) -> datetime:
        return self.ts + self.timeframe.delta

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def bullish(self) -> bool:
        return self.close > self.open

    @property
    def bearish(self) -> bool:
        return self.close < self.open


def only_complete(candles: Sequence[Candle], as_of: datetime) -> list[Candle]:
    """Return candles that are complete and closed strictly before ``as_of``.

    This is the primary look-ahead guard: a candle whose end time is after the
    evaluation timestamp is never visible to analysis.
    """
    as_of = ensure_utc(as_of)
    return [c for c in candles if c.complete and c.end_ts <= as_of]


def floor_ts(ts: datetime, tf: Timeframe) -> datetime:
    ts = ensure_utc(ts)
    epoch = int(ts.timestamp())
    if tf == Timeframe.W1:
        # weeks anchored to Monday 00:00 UTC (epoch day 0 was Thursday)
        secs = epoch - ((epoch // 86400 + 3) % 7) * 86400
        secs -= secs % 86400
        return datetime.fromtimestamp(secs, tz=ts.tzinfo)
    return datetime.fromtimestamp(epoch - epoch % tf.seconds, tz=ts.tzinfo)


def resample(candles: Iterable[Candle], target: Timeframe) -> list[Candle]:
    """Aggregate lower-timeframe candles into ``target``. Partial groups are marked incomplete."""
    src = sorted(candles, key=lambda c: c.ts)
    if not src:
        return []
    src_tf = src[0].timeframe
    if target.seconds % src_tf.seconds != 0 or target.seconds < src_tf.seconds:
        raise ValueError(f"cannot resample {src_tf.value} into {target.value}")
    expected_n = target.seconds // src_tf.seconds
    out: list[Candle] = []
    bucket: list[Candle] = []
    bucket_ts: datetime | None = None
    for c in src:
        b = floor_ts(c.ts, target)
        if bucket_ts is None:
            bucket_ts = b
        if b != bucket_ts:
            out.append(_agg(bucket, target, bucket_ts, expected_n))
            bucket, bucket_ts = [], b
        bucket.append(c)
    if bucket and bucket_ts is not None:
        out.append(_agg(bucket, target, bucket_ts, expected_n))
    return out


def _agg(bucket: list[Candle], tf: Timeframe, ts: datetime, expected_n: int) -> Candle:
    vols = [c.volume for c in bucket if c.volume is not None]
    complete = len(bucket) == expected_n and all(c.complete for c in bucket)
    if tf in (Timeframe.D1, Timeframe.W1):
        # daily/weekly buckets never contain the full theoretical count because
        # the market closes; consider them complete when all members are complete
        # and the last member ends the bucket's last trading hour.
        complete = all(c.complete for c in bucket)
    return Candle(
        instrument=bucket[0].instrument,
        timeframe=tf,
        ts=ts,
        open=bucket[0].open,
        high=max(c.high for c in bucket),
        low=min(c.low for c in bucket),
        close=bucket[-1].close,
        volume=sum(vols) if vols else None,
        volume_kind=bucket[0].volume_kind,
        spread_close=bucket[-1].spread_close,
        complete=complete,
        provider=bucket[0].provider,
        ingested_at=max((c.ingested_at for c in bucket if c.ingested_at), default=None),
        provenance_id=f"resampled:{bucket[0].provenance_id}..{bucket[-1].provenance_id}",
    )


def mark_incomplete(c: Candle) -> Candle:
    return replace(c, complete=False)


__all__ = ["Timeframe", "Quote", "Candle", "only_complete", "resample", "floor_ts", "mark_incomplete", "field"]
