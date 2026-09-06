"""Mock market-data provider (DEMO DATA). Deterministic, seeded, clearly labelled.

Backed by one cached synthetic path; every request is a numpy slice and only
the requested candles are materialised.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ...core.candles import Candle, Quote, Timeframe
from ...core.timeutil import ensure_utc
from ..base import MarketDataProvider, ProviderDoc, ProviderError, ProviderHealth
from .synth import PROVIDER, SynthParams, SynthPath, candles_from_arrays, generate_path, quote_at, resample_path

UTC = UTC


class MockMarketDataProvider(MarketDataProvider):
    name = PROVIDER
    is_mock = True
    doc = ProviderDoc(
        fields=["open", "high", "low", "close", "tick_volume_proxy", "spread_close", "bid", "ask"],
        frequency="1 minute synthetic",
        latency="none (generated)",
        historical_depth="from 2024-01-01 synthetic",
        revision_behaviour="none",
        licensing="none - synthetic",
        rate_limit="none",
        cost_category="free",
        failure_behaviour="raises ProviderError only on injected failure",
        backup_options=[],
        suitable_for_scalping=False,
    )

    def __init__(self, params: SynthParams | None = None, event_windows: list[tuple[datetime, datetime]] | None = None):
        self.params = params or SynthParams()
        self.event_windows = event_windows or []
        self._path: SynthPath | None = None
        self._tf_cache: dict[Timeframe, tuple[int, tuple]] = {}
        self._last_ok: datetime | None = None
        self.fail_next = False  # failure-injection hook for tests

    def _ensure(self, end: datetime) -> SynthPath:
        target = (end + timedelta(days=45)).replace(hour=0, minute=0, second=0, microsecond=0)
        if self._path is None or self._path.end_minute < int((end - datetime(2024, 1, 1, tzinfo=UTC)).total_seconds() // 60) + 2:
            self._path = generate_path(target, self.params, self.event_windows)
            self._tf_cache.clear()
        return self._path

    def _arrays(self, tf: Timeframe, path: SynthPath) -> tuple:
        cached = self._tf_cache.get(tf)
        if cached and cached[0] == path.end_minute:
            return cached[1]
        arrays = resample_path(path, tf)
        self._tf_cache[tf] = (path.end_minute, arrays)
        return arrays

    def get_candles(self, instrument: str, timeframe: Timeframe, start: datetime, end: datetime) -> list[Candle]:
        if self.fail_next:
            self.fail_next = False
            raise ProviderError("injected failure")
        start, end = ensure_utc(start), ensure_utc(end)
        path = self._ensure(end)
        out = candles_from_arrays(timeframe, self._arrays(timeframe, path), start, end + timedelta(minutes=1), end, path)
        self._last_ok = end
        return out

    def get_quote(self, instrument: str, now: datetime) -> Quote:
        now = ensure_utc(now)
        m1 = self.get_candles(instrument, Timeframe.M1, now - timedelta(hours=72), now)
        closed = [c for c in m1 if c.complete]
        last_close = closed[-1].close if closed else self.params.start_price
        return quote_at(now, last_close, self.params, self.event_windows)

    def median_spread(self, instrument: str, now: datetime) -> float | None:
        return self.params.base_spread

    def health(self) -> ProviderHealth:
        return ProviderHealth(self.name, self.kind, True, True, self._last_ok, None, 0.0, 0, ["DEMO DATA - synthetic prices"])
