"""Twelve Data XAU/USD adapter (REAL PROVIDER INTERFACE).

Status: implemented against the documented REST endpoints but NOT verified in
this build (no credentials were available). Do not treat it as working until
it has been exercised against a live key and the licence terms have been
reviewed. Licensing, rate limits and costs are documented in
docs/09-provider-licensing-and-cost-checklist.md.
"""
from __future__ import annotations

import time as _time
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
        rate_limit="credits per minute by plan",
        cost_category="paid (free tier for development only)",
        failure_behaviour="ProviderError / RateLimited; no data invented",
        backup_options=["OANDA v20 (bid/ask)", "Polygon.io forex", "broker feed"],
        suitable_for_scalping=False,
    )

    def __init__(self, api_key: str, base_url: str = "https://api.twelvedata.com", timeout: float = 10.0, max_retries: int = 3):
        if not api_key:
            raise ProviderError("TWELVEDATA_API_KEY missing")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_ok: datetime | None = None
        self._last_error: str | None = None
        self._failures = 0
        self._latency: float | None = None

    def _get(self, path: str, params: dict) -> dict:
        params = params | {"apikey": self.api_key, "format": "JSON"}
        delay = 1.0
        for attempt in range(self.max_retries):
            t0 = _time.perf_counter()
            try:
                r = httpx.get(f"{self.base_url}/{path}", params=params, timeout=self.timeout)
                self._latency = (_time.perf_counter() - t0) * 1000
                if r.status_code == 429:
                    raise RateLimited("rate limited")
                r.raise_for_status()
                data = r.json()
                if isinstance(data, dict) and data.get("status") == "error":
                    raise ProviderError(data.get("message", "provider error"))
                self._last_ok = datetime.now(tz=UTC)
                self._failures = 0
                return data
            except (httpx.HTTPError, RateLimited, ProviderError) as exc:
                self._failures += 1
                self._last_error = str(exc)
                if attempt == self.max_retries - 1:
                    raise ProviderError(f"twelvedata request failed: {exc}") from exc
                _time.sleep(delay)
                delay *= 2
        raise ProviderError("unreachable")

    def get_candles(self, instrument: str, timeframe: Timeframe, start: datetime, end: datetime) -> list[Candle]:
        start, end = ensure_utc(start), ensure_utc(end)
        data = self._get("time_series", {"symbol": "XAU/USD", "interval": _TF_MAP[timeframe], "start_date": start.strftime("%Y-%m-%d %H:%M:%S"), "end_date": end.strftime("%Y-%m-%d %H:%M:%S"), "timezone": "UTC", "outputsize": 5000})
        ingested = datetime.now(tz=UTC)
        out: list[Candle] = []
        for row in reversed(data.get("values", [])):
            ts = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S" if " " in row["datetime"] else "%Y-%m-%d").replace(tzinfo=UTC)
            c = Candle("XAUUSD", timeframe, ts, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]), None, "none", None, ts + timeframe.delta <= ingested, self.name, ingested, f"twelvedata:{timeframe.value}:{row['datetime']}")
            out.append(c)
        return out

    def get_quote(self, instrument: str, now: datetime) -> Quote:
        # Twelve Data's price endpoint returns a mid price only. Bid/ask are not available on all plans:
        # this adapter therefore reports a *synthetic spread of zero* which the integrity engine flags
        # (QUOTE_ZERO_SPREAD -> DEGRADED) so the user sees that execution costs are not observed.
        data = self._get("price", {"symbol": "XAU/USD"})
        px = float(data["price"])
        ingested = datetime.now(tz=UTC)
        return Quote("XAUUSD", px, px, ingested, self.name, ingested, provenance_id=f"twelvedata:price:{ingested.isoformat()}")

    def health(self) -> ProviderHealth:
        ok = self._failures < 3
        return ProviderHealth(self.name, self.kind, ok, False, self._last_ok, self._last_error, self._latency, self._failures, ["UNVERIFIED adapter: exercise against a live key before relying on it", "quote endpoint is mid-only; no observed spread"])
