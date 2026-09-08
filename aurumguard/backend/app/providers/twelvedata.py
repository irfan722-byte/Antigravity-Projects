"""Twelve Data XAU/USD adapter (REAL PROVIDER INTERFACE).

Status: implemented against the documented REST endpoints. It could not be
exercised inside the build sandbox (no outbound network), so run
``python -m app.check_provider`` with a real key before relying on it.
Licensing, rate limits and costs: docs/09-provider-licensing-and-cost-checklist.md.

Credit budget. Every HTTP call costs one API credit. Without caching the
analysis loop would spend (1 quote + 5 timeframes) credits per run, about
8,600 a day at a 60-second interval, far above the free tier (8 per minute,
800 per day). This adapter therefore:

* caches candles per timeframe and refetches only after a new bar of that
  timeframe could have closed (M5 every 5 min, H1 hourly, D1 daily, ...);
* caches the quote for ``quote_ttl_seconds`` so browser polling never reaches
  the provider, while the analysis loop asks for a fresher quote via
  ``max_age`` (the integrity engine's staleness limit).

Approximate daily usage at ANALYSIS_INTERVAL_SECONDS=300: 288 quotes plus
about 415 candle refreshes, roughly 700 credits. At 60 s: about 1,850, which
needs a paid plan.

Bid/ask. The price endpoint returns a mid price only. The adapter reports
``mid -/+ assumed_spread_usd/2`` and labels it as an assumption in the quote
provenance and health notes. It is a cost assumption for paper trading, not an
observed market spread; set it to 0 to report a zero spread and let the
integrity engine flag QUOTE_ZERO_SPREAD instead.
"""
from __future__ import annotations

import time as _time
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from ..core.candles import Candle, Quote, Timeframe
from ..core.timeutil import ensure_utc
from .base import MarketDataProvider, ProviderDoc, ProviderError, ProviderHealth, RateLimited

UTC = UTC
_TF_MAP = {
    Timeframe.M1: "1min",
    Timeframe.M5: "5min",
    Timeframe.M15: "15min",
    Timeframe.M30: "30min",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1day",
    Timeframe.W1: "1week",
}
FREE_TIER_CREDITS_PER_DAY = 800
FREE_TIER_CREDITS_PER_MINUTE = 8


def _bar_floor(ts: datetime, tf: Timeframe) -> int:
    """Epoch seconds of the bar that contains ``ts``. Weeks start on Monday."""
    e = int(ensure_utc(ts).timestamp())
    if tf is Timeframe.W1:
        days = e // 86400
        monday = days - ((days + 3) % 7)  # 1970-01-01 was a Thursday
        return monday * 86400
    return e - e % tf.seconds


@dataclass
class _CandleCache:
    candles: list[Candle]
    window_start: datetime
    fetched_at: datetime


class TwelveDataProvider(MarketDataProvider):
    name = "twelvedata"
    is_mock = False
    doc = ProviderDoc(
        fields=["open", "high", "low", "close", "(no bid/ask on candles)", "price (quote endpoint, mid)"],
        frequency="1min+ candles; quote polling",
        latency="seconds to tens of seconds (plan dependent)",
        historical_depth="years (plan dependent)",
        revision_behaviour="none published; candles may be corrected",
        licensing="commercial API terms; verify redistribution and internal-use clauses",
        rate_limit="credits per minute and per day by plan (free: 8/min, 800/day)",
        cost_category="paid (free tier for development only)",
        failure_behaviour="ProviderError / RateLimited; no data invented",
        backup_options=["OANDA v20 (bid/ask)", "Polygon.io forex", "broker feed"],
        suitable_for_scalping=False,
    )

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.twelvedata.com",
        timeout: float = 10.0,
        max_retries: int = 3,
        quote_ttl_seconds: float = 300.0,
        assumed_spread_usd: float = 0.30,
        symbol: str = "XAU/USD",
        transport: httpx.BaseTransport | None = None,
    ):
        if not api_key:
            raise ProviderError("TWELVEDATA_API_KEY missing")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.quote_ttl_seconds = float(quote_ttl_seconds)
        self.assumed_spread_usd = max(0.0, float(assumed_spread_usd))
        self.symbol = symbol
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout, transport=transport)
        self._last_ok: datetime | None = None
        self._last_error: str | None = None
        self._failures = 0
        self._latency: float | None = None
        self._quote: Quote | None = None
        self._candles: dict[Timeframe, _CandleCache] = {}
        self.request_count = 0

    # ------------------------------------------------------------------ http --
    def _get(self, path: str, params: dict) -> dict:
        params = params | {"apikey": self.api_key, "format": "JSON"}
        delay = 1.0
        for attempt in range(self.max_retries):
            t0 = _time.perf_counter()
            try:
                self.request_count += 1
                r = self._client.get(f"/{path}", params=params)
                self._latency = (_time.perf_counter() - t0) * 1000
                if r.status_code == 429:
                    raise RateLimited("rate limited (HTTP 429): API credits exhausted for this minute or day")
                r.raise_for_status()
                data = r.json()
                if isinstance(data, dict) and data.get("status") == "error":
                    if int(data.get("code", 0) or 0) == 429:
                        raise RateLimited(f"rate limited: {data.get('message', '')}")
                    raise ProviderError(f"provider error {data.get('code', '')}: {data.get('message', 'unknown')}")
                self._last_ok = datetime.now(tz=UTC)
                self._failures = 0
                return data
            except RateLimited as exc:
                # Retrying inside the same minute only burns more credits.
                self._failures += 1
                self._last_error = str(exc)
                raise
            except (httpx.HTTPError, ProviderError, ValueError) as exc:
                self._failures += 1
                self._last_error = str(exc)
                if attempt == self.max_retries - 1:
                    raise ProviderError(f"twelvedata request failed: {exc}") from exc
                _time.sleep(delay)
                delay *= 2
        raise ProviderError("unreachable")

    # --------------------------------------------------------------- candles --
    def _fetch_candles(self, timeframe: Timeframe, start: datetime, end: datetime) -> list[Candle]:
        data = self._get(
            "time_series",
            {
                "symbol": self.symbol,
                "interval": _TF_MAP[timeframe],
                "start_date": start.strftime("%Y-%m-%d %H:%M:%S"),
                "end_date": end.strftime("%Y-%m-%d %H:%M:%S"),
                "timezone": "UTC",
                "outputsize": 5000,
                "order": "ASC",
            },
        )
        ingested = datetime.now(tz=UTC)
        rows = data.get("values", []) if isinstance(data, dict) else []
        out: list[Candle] = []
        for row in rows:
            raw_ts = row["datetime"]
            ts = datetime.strptime(raw_ts, "%Y-%m-%d %H:%M:%S" if " " in raw_ts else "%Y-%m-%d").replace(tzinfo=UTC)
            out.append(
                Candle(
                    "XAUUSD",
                    timeframe,
                    ts,
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    None,
                    "none",
                    None,
                    ts + timeframe.delta <= ingested,
                    self.name,
                    ingested,
                    f"twelvedata:{timeframe.value}:{raw_ts}",
                )
            )
        out.sort(key=lambda c: c.ts)
        return out

    def get_candles(self, instrument: str, timeframe: Timeframe, start: datetime, end: datetime) -> list[Candle]:
        start, end = ensure_utc(start), ensure_utc(end)
        if timeframe not in _TF_MAP:
            raise ProviderError(f"timeframe {timeframe.value} not supported by twelvedata adapter")
        entry = self._candles.get(timeframe)
        needs_wider_window = entry is not None and start < entry.window_start - timeframe.delta
        new_bar_started = entry is not None and _bar_floor(end, timeframe) > _bar_floor(entry.fetched_at, timeframe)
        if entry is None or needs_wider_window or new_bar_started:
            window_start = min(start, entry.window_start) if entry else start
            candles = self._fetch_candles(timeframe, window_start, end)
            entry = _CandleCache(candles, window_start, datetime.now(tz=UTC))
            self._candles[timeframe] = entry
        return [c for c in entry.candles if start <= c.ts <= end]

    # ----------------------------------------------------------------- quote --
    def get_quote(self, instrument: str, now: datetime, max_age: float | None = None) -> Quote:
        now = ensure_utc(now)
        ttl = self.quote_ttl_seconds if max_age is None else min(self.quote_ttl_seconds, float(max_age))
        cached = self._quote
        if cached is not None and 0 <= (now - cached.ts).total_seconds() < ttl:
            return cached
        data = self._get("price", {"symbol": self.symbol})
        try:
            px = float(data["price"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError(f"price endpoint returned no usable price: {data}") from exc
        ingested = datetime.now(tz=UTC)
        half = self.assumed_spread_usd / 2.0
        q = Quote(
            "XAUUSD",
            round(px - half, 3),
            round(px + half, 3),
            ingested,
            self.name,
            ingested,
            provenance_id=f"twelvedata:price:{ingested.isoformat()}:assumed_spread={self.assumed_spread_usd}",
        )
        self._quote = q
        return q

    def median_spread(self, instrument: str, now: datetime) -> float | None:
        return self.assumed_spread_usd if self.assumed_spread_usd > 0 else None

    # ---------------------------------------------------------------- health --
    def health(self) -> ProviderHealth:
        ok = self._failures < 3
        cached = ", ".join(f"{tf.value}:{len(e.candles)}" for tf, e in sorted(self._candles.items(), key=lambda kv: kv[0].seconds)) or "none"
        spread_note = f"assumed spread {self.assumed_spread_usd:.2f} USD (not observed)" if self.assumed_spread_usd > 0 else "zero spread reported (mid only; QUOTE_ZERO_SPREAD expected)"
        return ProviderHealth(
            self.name,
            self.kind,
            ok,
            False,
            self._last_ok,
            self._last_error,
            self._latency,
            self._failures,
            [
                "LIVE PRICES via Twelve Data; verify the key with `python -m app.check_provider`",
                spread_note,
                f"quote cache {self.quote_ttl_seconds:.0f}s; candle cache [{cached}]; API requests this process: {self.request_count}",
            ],
        )
