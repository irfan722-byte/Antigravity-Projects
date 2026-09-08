"""Verify the configured market-data provider with a live key before running the app.

Run from ``aurumguard/backend`` with the same ``.env`` the server uses:

    python -m app.check_provider

It fetches one quote and three candle batches, prints what came back, and
estimates the daily API-credit usage for the configured analysis interval.
Exit code 0 means the provider answered correctly; 1 means it did not.
"""
from __future__ import annotations

import sys
import time
from datetime import UTC, datetime, timedelta

from .config import get_settings
from .core.candles import Timeframe
from .core.integrity import validate_quote
from .providers.base import ProviderError
from .providers.registry import build_providers
from .services.snapshot import DEFAULT_TFS

UTC = UTC


def estimate_daily_credits(interval_seconds: int, quote_ttl_seconds: float, timeframes: list[Timeframe]) -> int:
    runs_per_day = 86400 / max(1, interval_seconds)
    quotes = 86400 / max(float(interval_seconds), quote_ttl_seconds)
    candles = sum(min(runs_per_day, 86400 / tf.seconds) for tf in timeframes)
    return int(round(quotes + candles))


def main() -> int:
    s = get_settings()
    print(f"[check] APP_ENV={s.app_env}  MARKET_DATA_PROVIDER={s.market_data_provider}  TWELVEDATA_API_KEY={'set' if s.twelvedata_api_key else 'MISSING'}")
    print(f"[check] CALENDAR_PROVIDER={s.calendar_provider}  NEWS_PROVIDER={s.news_provider}  MACRO_PROVIDER={s.macro_provider}  ANALYSIS_INTERVAL_SECONDS={s.analysis_interval_seconds}")
    problems = s.validate_for_environment()
    if problems:
        for p in problems:
            print(f"[check] CONFIG PROBLEM: {p}")
        return 1
    if s.market_data_provider == "mock":
        print("[check] mock market data selected; nothing external to verify. Set MARKET_DATA_PROVIDER=twelvedata and TWELVEDATA_API_KEY in .env for live prices.")
        return 0

    ps = build_providers(s)
    market = ps.market
    now = datetime.now(tz=UTC)
    ok = True

    try:
        t0 = time.perf_counter()
        q = market.get_quote("XAUUSD", now, max_age=0)
        ms = (time.perf_counter() - t0) * 1000
        rep = validate_quote(q, datetime.now(tz=UTC)).to_dict()
        print(f"[check] quote  bid={q.bid:.2f} ask={q.ask:.2f} spread={q.spread:.2f} ts={q.ts.isoformat(timespec='seconds')} provider={q.provider} ({ms:.0f} ms) integrity={rep.get('status')} issues={[i.get('code') for i in rep.get('issues', [])]}")
    except ProviderError as exc:
        print(f"[check] quote FAILED: {exc}")
        ok = False

    for tf, days in ((Timeframe.M5, 2), (Timeframe.H1, 20), (Timeframe.D1, 400)):
        try:
            t0 = time.perf_counter()
            candles = market.get_candles("XAUUSD", tf, now - timedelta(days=days), now)
            ms = (time.perf_counter() - t0) * 1000
            if not candles:
                print(f"[check] {tf.value:<3} returned 0 bars for the last {days} days ({ms:.0f} ms)")
                ok = False
                continue
            last = candles[-1]
            print(f"[check] {tf.value:<3} {len(candles)} bars; last {last.ts.isoformat(timespec='minutes')} O={last.open} H={last.high} L={last.low} C={last.close} complete={last.complete} ({ms:.0f} ms)")
        except ProviderError as exc:
            print(f"[check] {tf.value:<3} FAILED: {exc}")
            ok = False

    h = market.health()
    print(f"[check] health ok={h.ok} failures={h.consecutive_failures} last_error={h.last_error}")
    for note in h.notes:
        print(f"[check]   {note}")
    used = getattr(market, "request_count", None)
    if used is not None:
        print(f"[check] API requests used by this check: {used}")
    ttl = float(getattr(market, "quote_ttl_seconds", s.analysis_interval_seconds))
    est = estimate_daily_credits(s.analysis_interval_seconds, ttl, DEFAULT_TFS)
    print(f"[check] estimated credits/day at ANALYSIS_INTERVAL_SECONDS={s.analysis_interval_seconds}: about {est} (Twelve Data free tier: 800/day, 8/minute)")
    if est > 800:
        print("[check]   above the free tier: raise ANALYSIS_INTERVAL_SECONDS to 300 or use a paid plan")
    print("[check] RESULT: OK" if ok else "[check] RESULT: FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
