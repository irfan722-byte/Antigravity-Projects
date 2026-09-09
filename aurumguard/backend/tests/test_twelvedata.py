"""Twelve Data adapter: credit-saving cache behaviour, quote freshness, error paths.

Uses an in-process httpx transport; no network. The live API itself is verified
separately with `python -m app.check_provider`.
"""
from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.check_provider import estimate_daily_credits, lookback_days, smallest_affordable_interval
from app.config import Settings
from app.core.candles import Timeframe
from app.providers.base import ProviderError, RateLimited
from app.providers.none import NoCalendarProvider, NoNewsProvider
from app.providers.registry import build_providers
from app.providers.twelvedata import FREE_TIER_CREDITS_PER_DAY, TwelveDataProvider, _bar_floor
from app.services.snapshot import DEFAULT_TFS

UTC = UTC


class FakeTwelveData:
    """Minimal stand-in for the two endpoints the adapter uses."""

    def __init__(self, price: float = 2400.5, bars_ending_at: datetime | None = None):
        self.price = price
        self.calls: list[str] = []
        self.status_code = 200
        self.body_override: dict | None = None
        end = bars_ending_at or datetime.now(tz=UTC)
        self.end = end

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request.url.path)
        if self.body_override is not None or self.status_code != 200:
            return httpx.Response(self.status_code, json=self.body_override or {})
        if request.url.path == "/price":
            return httpx.Response(200, json={"price": str(self.price)})
        interval = request.url.params.get("interval")
        step = {"5min": 300, "15min": 900, "1h": 3600, "4h": 14400, "1day": 86400}[interval]
        last_open = _bar_floor(self.end, {"5min": Timeframe.M5, "15min": Timeframe.M15, "1h": Timeframe.H1, "4h": Timeframe.H4, "1day": Timeframe.D1}[interval])
        values = []
        for i in range(3):
            ts = datetime.fromtimestamp(last_open - i * step, tz=UTC)
            fmt = "%Y-%m-%d" if interval == "1day" else "%Y-%m-%d %H:%M:%S"
            values.append({"datetime": ts.strftime(fmt), "open": "2400", "high": "2405", "low": "2395", "close": str(2400 + i)})
        return httpx.Response(200, json={"meta": {"symbol": "XAU/USD"}, "values": values, "status": "ok"})


def make(fake: FakeTwelveData, **kw) -> TwelveDataProvider:
    return TwelveDataProvider("test-key", transport=httpx.MockTransport(fake.handler), max_retries=1, **kw)


def test_candles_are_cached_until_a_new_bar_starts():
    now = datetime.now(tz=UTC)
    fake = FakeTwelveData(bars_ending_at=now)
    p = make(fake)
    first = p.get_candles("XAUUSD", Timeframe.M5, now - timedelta(hours=1), now)
    assert len(first) == 3 and first[0].ts < first[-1].ts and first[-1].provider == "twelvedata"
    assert p.request_count == 1
    again = p.get_candles("XAUUSD", Timeframe.M5, now - timedelta(hours=1), now)  # same bar: served from cache
    assert again == first and p.request_count == 1
    p.get_candles("XAUUSD", Timeframe.M5, now - timedelta(hours=1), now + timedelta(minutes=6))  # next M5 bar has started
    assert p.request_count == 2
    p.get_candles("XAUUSD", Timeframe.M5, now - timedelta(hours=3), now + timedelta(minutes=6))  # wider window than cached
    assert p.request_count == 3
    p.get_candles("XAUUSD", Timeframe.H1, now - timedelta(days=2), now)  # different timeframe: its own cache
    assert p.request_count == 4
    assert all(path == "/time_series" for path in fake.calls)


def test_daily_bars_parse_date_only_timestamps():
    now = datetime.now(tz=UTC)
    p = make(FakeTwelveData(bars_ending_at=now))
    bars = p.get_candles("XAUUSD", Timeframe.D1, now - timedelta(days=10), now)
    assert len(bars) == 3 and bars[-1].ts.hour == 0 and bars[-1].timeframe is Timeframe.D1


def test_quote_cache_and_max_age():
    now = datetime.now(tz=UTC)
    fake = FakeTwelveData(price=2400.5)
    p = make(fake, quote_ttl_seconds=300, assumed_spread_usd=0.30)
    q = p.get_quote("XAUUSD", now)
    assert p.request_count == 1 and q.bid == pytest.approx(2400.35) and q.ask == pytest.approx(2400.65)
    assert q.spread == pytest.approx(0.30) and "assumed_spread" in q.provenance_id
    assert p.get_quote("XAUUSD", now + timedelta(seconds=100)) is q  # UI polling: cached
    assert p.request_count == 1
    fresh = p.get_quote("XAUUSD", now + timedelta(seconds=100), max_age=20)  # analysis loop: fresh
    assert fresh is not q and p.request_count == 2
    p.get_quote("XAUUSD", now + timedelta(seconds=500))  # cache expired
    assert p.request_count == 3
    assert p.median_spread("XAUUSD", now) == pytest.approx(0.30)


def test_zero_assumed_spread_reports_mid_only():
    p = make(FakeTwelveData(price=2400.0), assumed_spread_usd=0.0)
    q = p.get_quote("XAUUSD", datetime.now(tz=UTC))
    assert q.bid == q.ask == 2400.0 and p.median_spread("XAUUSD", q.ts) is None


def test_rate_limit_is_not_retried():
    fake = FakeTwelveData()
    fake.status_code = 429
    p = TwelveDataProvider("k", transport=httpx.MockTransport(fake.handler), max_retries=3)
    with pytest.raises(RateLimited):
        p.get_quote("XAUUSD", datetime.now(tz=UTC))
    assert p.request_count == 1  # retrying inside the same minute would only burn credits
    fake.status_code = 200
    fake.body_override = {"code": 429, "status": "error", "message": "You have run out of API credits"}
    with pytest.raises(RateLimited):
        p.get_quote("XAUUSD", datetime.now(tz=UTC))
    assert not p.health().ok or p.health().consecutive_failures >= 2


def test_provider_error_payload_and_missing_key():
    fake = FakeTwelveData()
    fake.body_override = {"code": 401, "status": "error", "message": "invalid api key"}
    p = make(fake)
    with pytest.raises(ProviderError, match="invalid api key"):
        p.get_quote("XAUUSD", datetime.now(tz=UTC))
    with pytest.raises(ProviderError):
        TwelveDataProvider("")


def test_health_notes_describe_live_status():
    p = make(FakeTwelveData())
    h = p.health()
    assert h.ok and not h.is_mock and any("LIVE PRICES" in n for n in h.notes) and any("assumed spread" in n for n in h.notes)


def test_bar_floor_week_starts_monday():
    ts = datetime(2026, 9, 10, 15, 30, tzinfo=UTC)  # Thursday
    assert datetime.fromtimestamp(_bar_floor(ts, Timeframe.W1), tz=UTC) == datetime(2026, 9, 7, tzinfo=UTC)
    assert datetime.fromtimestamp(_bar_floor(ts, Timeframe.H4), tz=UTC) == datetime(2026, 9, 10, 12, tzinfo=UTC)


def test_free_tier_budget_estimate():
    # The analysis loop demands a quote fresher than the adapter's cache (max_age = the integrity
    # staleness limit), so it costs one credit per run however long the quote cache is.
    assert 600 < estimate_daily_credits(300, 20.0, DEFAULT_TFS) < FREE_TIER_CREDITS_PER_DAY
    assert estimate_daily_credits(60, 20.0, DEFAULT_TFS) > 1800  # the default 60 s interval does not fit
    fits = smallest_affordable_interval(20.0, DEFAULT_TFS)
    assert fits is not None and estimate_daily_credits(fits, 20.0, DEFAULT_TFS) <= FREE_TIER_CREDITS_PER_DAY
    assert estimate_daily_credits(fits - 15, 20.0, DEFAULT_TFS) > FREE_TIER_CREDITS_PER_DAY


def test_none_providers_return_nothing_and_are_wired_by_settings():
    now = datetime.now(tz=UTC)
    assert NoCalendarProvider().get_events(now, now + timedelta(days=7), now) == []
    assert NoNewsProvider().get_news(now - timedelta(days=1), now) == []
    ps = build_providers(Settings(calendar_provider="none", news_provider="none"))
    assert ps.calendar.name == "none" and ps.news.name == "none"
    assert ps.demo_mode is True and ps.data_mode == "DEMO"  # market still mock
    summary = ps.summary()
    assert summary["economic_calendar"]["disabled"] is True and summary["news"]["disabled"] is True
    assert summary["market_data"]["is_mock"] is True
    assert all(h.ok for h in ps.health())
    assert any("EVENT AWARENESS DISABLED" in n for n in ps.calendar.health().notes)
    assert json.dumps(summary)  # serialisable for /api/meta


def test_check_covers_every_timeframe_the_analysis_loop_uses():
    now = datetime.now(tz=UTC)
    fake = FakeTwelveData(bars_ending_at=now)
    p = make(fake)
    for tf in DEFAULT_TFS:
        days = lookback_days(tf)
        assert p.get_candles("XAUUSD", tf, now - timedelta(days=days), now), f"{tf.value} returned nothing"
    assert p.request_count == len(DEFAULT_TFS)  # one credit per timeframe, no repeats
    assert lookback_days(Timeframe.M5) == 2 and lookback_days(Timeframe.D1) == 301


def test_requests_stay_inside_the_per_minute_allowance():
    fake = FakeTwelveData()
    p = TwelveDataProvider("k", transport=httpx.MockTransport(fake.handler), credits_per_minute=2, max_rate_wait_seconds=0.0)
    now = datetime.now(tz=UTC)
    p.get_quote("XAUUSD", now, max_age=0)
    p.get_candles("XAUUSD", Timeframe.M5, now - timedelta(hours=1), now)
    assert p.request_count == 2
    with pytest.raises(RateLimited, match="local rate limit"):
        p.get_candles("XAUUSD", Timeframe.H1, now - timedelta(days=2), now)
    assert p.request_count == 2  # the third request was never sent, so no 429 and no wasted credit
    assert len(fake.calls) == 2


def test_a_cold_start_does_not_stampede_the_provider():
    """Scheduler thread and page requests hit an empty cache together: one fetch per timeframe."""
    now = datetime.now(tz=UTC)
    fake = FakeTwelveData(bars_ending_at=now)
    slow = threading.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        slow.wait(0.5)  # hold the first caller inside the fetch so the others pile up behind it
        return fake.handler(request)

    p = TwelveDataProvider("k", transport=httpx.MockTransport(handler), credits_per_minute=0)
    errors: list[BaseException] = []

    def work():
        try:
            p.get_quote("XAUUSD", now, max_age=20)  # what the analysis loop asks for
            for tf in (Timeframe.M5, Timeframe.M15, Timeframe.H1):
                p.get_candles("XAUUSD", tf, now - timedelta(days=3), now)
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    slow.set()
    for t in threads:
        t.join(10)
    assert not errors
    assert p.request_count == 4  # one quote + three timeframes, not 4 x 4


def test_a_quote_fetched_during_this_evaluation_is_reused():
    """build_snapshot stamps `now`, then fetches; the result is newer than `now` and must count as fresh."""
    fake = FakeTwelveData()
    p = make(fake)
    now = datetime.now(tz=UTC)
    first = p.get_quote("XAUUSD", now, max_age=20)
    assert first.ts >= now  # ingested after the caller took its timestamp
    assert p.get_quote("XAUUSD", now, max_age=20) is first
    assert p.request_count == 1
