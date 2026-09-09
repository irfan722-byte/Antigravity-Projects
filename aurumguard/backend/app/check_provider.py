"""Verify the configured market-data provider with a live key before running the app.

Run from ``aurumguard/backend`` with the same ``.env`` the server uses:

    python -m app.check_provider

It fetches one quote and one candle batch for every timeframe the analysis loop
uses, prints what came back, and estimates the daily API-credit usage for the
configured analysis interval. Cost: one credit per timeframe plus one.
Exit code 0 means the provider answered correctly; 1 means it did not.
"""
from __future__ import annotations

import sys
import time
from datetime import UTC, datetime, timedelta

from .config import get_settings
from .core.candles import Timeframe
from .core.integrity import IntegrityConfig, validate_quote
from .core.tls import CERT_VERIFY_HINT, describe_peer_issuer
from .providers.base import ProviderError
from .providers.registry import build_providers
from .providers.twelvedata import FREE_TIER_CREDITS_PER_DAY, FREE_TIER_CREDITS_PER_MINUTE
from .services.snapshot import DEFAULT_TFS

UTC = UTC


def estimate_daily_credits(interval_seconds: int, quote_max_age_seconds: float, timeframes: list[Timeframe]) -> int:
    """Credits the analysis loop spends per day.

    One quote per run: the loop asks for a quote no older than the integrity engine's staleness
    limit (20 s by default), which is shorter than the adapter's quote cache, so the cache never
    answers it. Browser polling is free because it accepts the cached quote. Candles cost one
    credit per timeframe per bar close, capped at one per run.
    """
    runs_per_day = 86400 / max(1, interval_seconds)
    quotes = runs_per_day if quote_max_age_seconds < interval_seconds else 86400 / max(1.0, quote_max_age_seconds)
    candles = sum(min(runs_per_day, 86400 / tf.seconds) for tf in timeframes)
    return int(round(quotes + candles))


def lookback_days(tf: Timeframe, bars: int = 300, cap: int = 400) -> int:
    """Days of history needed for roughly ``bars`` bars of this timeframe."""
    return min(cap, max(2, int(bars * tf.seconds / 86400) + 1))


def smallest_affordable_interval(quote_max_age_seconds: float, timeframes: list[Timeframe], budget: int = FREE_TIER_CREDITS_PER_DAY) -> int | None:
    """Shortest analysis interval (rounded to 15 s) that stays inside the daily credit budget."""
    for interval in range(15, 3601, 15):
        if estimate_daily_credits(interval, quote_max_age_seconds, timeframes) <= budget:
            return interval
    return None


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
    print(f"[check] HTTPS trust: {getattr(market, 'trust', 'certifi bundle')}")
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

    # Every timeframe the analysis loop uses, not a sample: an interval the provider spells
    # differently (M15, H4) would otherwise only surface as DATA UNAVAILABLE after startup.
    for tf in DEFAULT_TFS:
        days = lookback_days(tf)
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
    est = estimate_daily_credits(s.analysis_interval_seconds, IntegrityConfig().quote_max_age_seconds, DEFAULT_TFS)
    print(f"[check] estimated credits/day at ANALYSIS_INTERVAL_SECONDS={s.analysis_interval_seconds}: about {est} (Twelve Data free tier: {FREE_TIER_CREDITS_PER_DAY}/day, {FREE_TIER_CREDITS_PER_MINUTE}/minute)")
    if est > FREE_TIER_CREDITS_PER_DAY:
        fits = smallest_affordable_interval(IntegrityConfig().quote_max_age_seconds, DEFAULT_TFS)
        advice = f"Set ANALYSIS_INTERVAL_SECONDS to at least {fits} in .env" if fits else "Reduce the number of timeframes"
        print(f"[check]   ABOVE THE FREE TIER: the feed would stop part-way through the day. {advice}, or use a paid plan.")
    if not ok and "certificate verification failed" in (h.last_error or "").lower():
        print("[check] The key was never used: the connection failed before the request was sent.")
        issuer = describe_peer_issuer("api.twelvedata.com")
        if issuer:
            print(f"[check] The certificate this machine is served comes from: {issuer}")
        for line in CERT_VERIFY_HINT.split("; "):
            print(f"[check]   {line}")
    print("[check] RESULT: OK" if ok else "[check] RESULT: FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
